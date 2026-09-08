import type { AxiosError } from "axios";

import { CSRF_HEADER_NAME, DEFAULT_CSRF_COOKIE_NAME, MUTATING_HTTP_METHODS } from "./constants";
import { readCookie } from "./cookieUtils";
import type { AuthAdapter, LoginSuccessResponse, RetryableRequestConfig } from "./types";

type MutatingMethod = (typeof MUTATING_HTTP_METHODS)[number];

function isMutatingMethod(method: string): method is MutatingMethod {
	return (MUTATING_HTTP_METHODS as readonly string[]).includes(method);
}

/**
 * sessionモード用アダプタ。
 * 認証情報はブラウザが保持するCookieに委ね、更新系リクエストにのみCSRFヘッダを付与する。
 */
export class SessionAdapter implements AuthAdapter {
	readonly mode = "session" as const;

	constructor(private readonly csrfCookieName: string = DEFAULT_CSRF_COOKIE_NAME) {}

	attach(config: RetryableRequestConfig): RetryableRequestConfig {
		const method = (config.method ?? "get").toLowerCase();
		const next: RetryableRequestConfig = { ...config, withCredentials: true };

		if (isMutatingMethod(method)) {
			const csrfToken = readCookie(this.csrfCookieName);
			if (csrfToken) {
				next.headers = { ...next.headers, [CSRF_HEADER_NAME]: csrfToken };
			}
		}

		return next;
	}

	onLoginSuccess(response: LoginSuccessResponse): void {
		// Cookieはブラウザが保持するため何もしない
		void response;
	}

	async onUnauthorized(error: AxiosError): Promise<boolean> {
		// sessionモードはリフレッシュの概念がなく、401は即ログアウト扱いとする
		void error;
		return false;
	}

	async restoreSession(): Promise<boolean> {
		return true;
	}

	onLogout(): void {
		// Cookie破棄はbackendのlogoutに任せる
	}
}
