import { createAuthAdapter } from "./index";
import type { AuthAdapter, AuthMode, TokenStore } from "./types";

const DEFAULT_API_BASE_URL = "/api";

export type AuthConfigResponse = {
	auth_mode: AuthMode;
	csrf_cookie_name?: string;
};

let authAdapter: AuthAdapter | null = null;
let authConfigRequest: Promise<AuthAdapter> | null = null;
let accessToken: string | null = null;

const runtimeTokenStore: TokenStore = {
	getAccessToken: () => accessToken,
	setAccessToken: (token) => {
		accessToken = token;
	},
};

function isAuthMode(value: unknown): value is AuthMode {
	return value === "session" || value === "jwt";
}

function toHeaderRecord(headers: Headers): Record<string, string> {
	const result: Record<string, string> = {};
	headers.forEach((value, key) => {
		result[key] = value;
	});
	return result;
}

function toFetchHeaders(headers: unknown): Headers {
	const result = new Headers();
	if (!headers || typeof headers !== "object") {
		return result;
	}
	Object.entries(headers as Record<string, unknown>).forEach(([key, value]) => {
		if (typeof value === "string") {
			result.set(key, value);
		}
	});
	return result;
}

export function setAuthAdapterMode(mode: AuthMode, csrfCookieName?: string): void {
	authAdapter = createAuthAdapter(mode, {
		csrfCookieName,
		tokenStore: runtimeTokenStore,
	});
}

export function setAuthAccessToken(token: string | null): void {
	runtimeTokenStore.setAccessToken(token);
}

export function clearAuthAdapter(): void {
	authAdapter = null;
	authConfigRequest = null;
	runtimeTokenStore.setAccessToken(null);
}

export async function resolveAuthAdapter(
	apiBaseUrl: string = DEFAULT_API_BASE_URL,
	fetchImpl: typeof fetch = fetch,
): Promise<AuthAdapter> {
	if (authAdapter) {
		return authAdapter;
	}
	if (authConfigRequest) {
		return authConfigRequest;
	}

	const request = fetchImpl(`${apiBaseUrl}/auth/config`, {
		method: "GET",
		credentials: "same-origin",
		headers: { Accept: "application/json" },
	})
		.then(async (response) => {
			if (!response.ok) {
				throw new Error(`auth config request failed: ${response.status}`);
			}
			const config = (await response.json()) as Partial<AuthConfigResponse>;
			if (!isAuthMode(config.auth_mode)) {
				throw new Error("auth config response has an invalid auth_mode");
			}
			setAuthAdapterMode(config.auth_mode, config.csrf_cookie_name);
			return authAdapter as AuthAdapter;
		});
	authConfigRequest = request.finally(() => {
		authConfigRequest = null;
	});
	return authConfigRequest;
}

export async function fetchWithAuth(
	url: string,
	init: RequestInit = {},
	apiBaseUrl: string = DEFAULT_API_BASE_URL,
): Promise<Response> {
	const adapter = await resolveAuthAdapter(apiBaseUrl);
	const headers = new Headers(init.headers);
	const attached = adapter.attach({
		method: init.method ?? "GET",
		url,
		headers: toHeaderRecord(headers),
	});

	return fetch(url, {
		...init,
		credentials: attached.withCredentials ? "include" : "same-origin",
		headers: toFetchHeaders(attached.headers),
	});
}
