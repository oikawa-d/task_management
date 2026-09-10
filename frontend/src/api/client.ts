import axios, { type AxiosInstance } from "axios";

import { AUTH_OAUTH_EXCHANGE_ENDPOINT, LOGIN_ENDPOINT_PATH, REFRESH_EXEMPT_PATHS } from "./authAdapter/constants";
import type { AuthAdapter, RetryableRequestConfig } from "./authAdapter";
import { getApiClientConfig } from "./config";
import { toApiError } from "./errors";

const LOGIN_SUCCESS_PATHS = [LOGIN_ENDPOINT_PATH, AUTH_OAUTH_EXCHANGE_ENDPOINT] as const;

export interface ApiClientOptions {
	authAdapter?: AuthAdapter;
	onLogout?: () => void;
	baseURL?: string;
	timeoutMs?: number;
}

interface ApiClientRuntime {
	authAdapter?: AuthAdapter;
	onLogout?: () => void;
}

const runtimes = new WeakMap<AxiosInstance, ApiClientRuntime>();

function toPathSegments(path: string): string[] {
	return path.split("/").filter(Boolean);
}

/** クエリ・ハッシュを除いたパスのセグメントが末尾で完全一致する場合のみtrueにする（部分一致による誤一致を防ぐ）。 */
function matchesPath(url: string | undefined, paths: readonly string[]): boolean {
	if (!url) {
		return false;
	}
	const pathname = url.split(/[?#]/)[0] ?? "";
	const urlSegments = toPathSegments(pathname);
	return paths.some((path) => {
		const pathSegments = toPathSegments(path);
		if (pathSegments.length > urlSegments.length) {
			return false;
		}
		const tail = urlSegments.slice(urlSegments.length - pathSegments.length);
		return tail.every((segment, index) => segment === pathSegments[index]);
	});
}

function configureRuntime(client: AxiosInstance, options: ApiClientOptions): ApiClientRuntime {
	const runtime = runtimes.get(client) ?? {};
	runtime.authAdapter = options.authAdapter ?? runtime.authAdapter;
	runtime.onLogout = options.onLogout ?? runtime.onLogout;
	runtimes.set(client, runtime);
	return runtime;
}

function installInterceptors(client: AxiosInstance, runtime: ApiClientRuntime): void {
	client.interceptors.request.use((config) => {
		if (!runtime.authAdapter) {
			return config;
		}
		return runtime.authAdapter.attach(config as RetryableRequestConfig) as typeof config;
	});

	client.interceptors.response.use(
		(response) => {
			if (runtime.authAdapter && matchesPath(response.config.url, LOGIN_SUCCESS_PATHS)) {
				runtime.authAdapter.onLoginSuccess(response.data);
			}
			return response;
		},
		async (error: unknown) => {
			if (axios.isAxiosError(error) && error.response?.status === 401 && error.config && runtime.authAdapter) {
				let shouldRetry = false;
				try {
					shouldRetry = await runtime.authAdapter.onUnauthorized(error);
				} catch {
					shouldRetry = false;
				}

				if (shouldRetry) {
					return client.request(error.config as RetryableRequestConfig);
				}

				if (!matchesPath(error.config.url, REFRESH_EXEMPT_PATHS)) {
					runtime.authAdapter.onLogout();
					runtime.onLogout?.();
				}
			}

			return Promise.reject(toApiError(error));
		},
	);
}

export function createApiClient(options: ApiClientOptions = {}): AxiosInstance {
	const config = getApiClientConfig();
	const client = axios.create({
		baseURL: options.baseURL ?? config.baseURL,
		timeout: options.timeoutMs ?? config.timeoutMs,
		headers: { "Content-Type": "application/json" },
	});
	const runtime = configureRuntime(client, options);
	installInterceptors(client, runtime);
	return client;
}

export function configureApiClient(client: AxiosInstance, options: ApiClientOptions): AxiosInstance {
	const runtime = runtimes.get(client);
	if (!runtime) {
		const configuredRuntime = configureRuntime(client, options);
		installInterceptors(client, configuredRuntime);
		return client;
	}
	configureRuntime(client, options);
	return client;
}

let sharedClient: AxiosInstance | undefined;

/** feature/API層が同じ認証・エラー処理を使うための共有クライアント。 */
export function getApiClient(options: ApiClientOptions = {}): AxiosInstance {
	if (!sharedClient) {
		sharedClient = createApiClient(options);
	} else if (options.authAdapter || options.onLogout) {
		configureApiClient(sharedClient, options);
	}
	return sharedClient;
}

/** テスト間で共有clientの状態を分離するためのリセット。 */
export function resetApiClient(): void {
	sharedClient = undefined;
}
