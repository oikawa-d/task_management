import axios, { type AxiosError, type AxiosInstance } from "axios";

import {
	CSRF_HEADER_NAME,
	DEFAULT_CSRF_COOKIE_NAME,
	LOGOUT_ENDPOINT_PATH,
	REFRESH_ENDPOINT_PATH,
	REFRESH_EXEMPT_PATHS,
} from "./constants";
import { readCookie } from "./cookieUtils";
import type { AuthAdapter, LoginSuccessResponse, RetryableRequestConfig, TokenStore } from "./types";

function isRefreshExemptPath(url: string | undefined): boolean {
	if (!url) {
		return false;
	}
	return REFRESH_EXEMPT_PATHS.some((exemptPath) => url.includes(exemptPath));
}

function isCookieAuthenticatedPath(url: string | undefined): boolean {
	if (!url) {
		return false;
	}
	return url.includes(REFRESH_ENDPOINT_PATH) || url.includes(LOGOUT_ENDPOINT_PATH);
}

/** authStore未実装のため既定で使う、メモリのみのトークン保持実装 */
function createInMemoryTokenStore(): TokenStore {
	let accessToken: string | null = null;
	return {
		getAccessToken: () => accessToken,
		setAccessToken: (token) => {
			accessToken = token;
		},
	};
}

/**
 * jwtモード用アダプタ。
 * アクセストークンはメモリ（注入されたTokenStore）に保持し、401時は /auth/refresh を
 * 1回だけ試行する。同時に発生した401は進行中のrefreshPromiseを共有して多重実行を防ぐ。
 */
export class JwtAdapter implements AuthAdapter {
	readonly mode = "jwt" as const;

	private refreshPromise: Promise<boolean> | null = null;

	constructor(
		private readonly tokenStore: TokenStore = createInMemoryTokenStore(),
		private readonly httpClient: AxiosInstance = axios,
		private readonly csrfCookieName: string = DEFAULT_CSRF_COOKIE_NAME,
	) {}

	attach(config: RetryableRequestConfig): RetryableRequestConfig {
		const next: RetryableRequestConfig = { ...config };

		if (isCookieAuthenticatedPath(config.url)) {
			next.withCredentials = true;
			const csrfToken = readCookie(this.csrfCookieName);
			if (csrfToken) {
				next.headers = { ...next.headers, [CSRF_HEADER_NAME]: csrfToken };
			}
			return next;
		}

		const accessToken = this.tokenStore.getAccessToken();
		if (accessToken) {
			next.headers = { ...next.headers, Authorization: `Bearer ${accessToken}` };
		}
		return next;
	}

	onLoginSuccess(response: LoginSuccessResponse): void {
		if (response.access_token) {
			this.tokenStore.setAccessToken(response.access_token);
		}
	}

	async onUnauthorized(error: AxiosError): Promise<boolean> {
		const config = error.config as RetryableRequestConfig | undefined;

		if (!config || config._retried || isRefreshExemptPath(config.url)) {
			return false;
		}

		config._retried = true;

		if (!this.refreshPromise) {
			this.refreshPromise = this.refresh();
		}

		return this.refreshPromise;
	}

	async restoreSession(): Promise<boolean> {
		if (!this.refreshPromise) {
			this.refreshPromise = this.refresh();
		}
		return this.refreshPromise;
	}

	onLogout(): void {
		this.tokenStore.setAccessToken(null);
	}

	private async refresh(): Promise<boolean> {
		try {
			const csrfToken = readCookie(this.csrfCookieName);
			const response = await this.httpClient.post<LoginSuccessResponse>(
				REFRESH_ENDPOINT_PATH,
				undefined,
				{
					withCredentials: true,
					headers: csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : undefined,
				},
			);

			if (response.data?.access_token) {
				this.tokenStore.setAccessToken(response.data.access_token);
			}
			return true;
		} catch {
			this.tokenStore.setAccessToken(null);
			return false;
		} finally {
			this.refreshPromise = null;
		}
	}
}
