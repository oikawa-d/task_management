import { fetchWithAuth } from "../../../api/authAdapter/client";
import {
	AUTH_ME_ENDPOINT,
	AUTH_OAUTH_EXCHANGE_ENDPOINT,
} from "../../../api/authAdapter/constants";
import type { AuthUserRole } from "../../../auth/authStore";

/**
 * design doc: docs/detailed_design/api/auth/13_post_auth_oauth_exchange.md §3
 * design doc: docs/detailed_design/api/auth/04_get_auth_me.md
 *
 * バックエンドのエラーレスポンス形式（docs/basic_design/04_api.md §4.1）に沿って
 * `error.code` を保持し、呼び出し側でエラーコード別の表示分岐を行えるようにする。
 */
export class OAuthCallbackApiError extends Error {
	readonly status: number;
	readonly code: string | undefined;

	constructor(status: number, code: string | undefined) {
		super(`oauth callback api request failed: ${status} ${code ?? ""}`.trim());
		this.name = "OAuthCallbackApiError";
		this.status = status;
		this.code = code;
	}
}

async function readErrorCode(response: Response): Promise<string | undefined> {
	try {
		const body = (await response.json()) as { error?: { code?: string } };
		return body.error?.code;
	} catch {
		return undefined;
	}
}

const DEFAULT_API_BASE_URL = "/api";

function getApiBaseUrl(): string {
	return import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
}

export type OAuthExchangeResult = {
	access_token: string;
	token_type: string;
	expires_in: number;
	redirect_to: string;
};

/** jwtモード専用。ハンドオフコードをアクセストークン・Cookieへ交換する */
export async function oauthExchange(code: string, signal?: AbortSignal): Promise<OAuthExchangeResult> {
	const baseUrl = getApiBaseUrl();
	const response = await fetchWithAuth(
		`${baseUrl}${AUTH_OAUTH_EXCHANGE_ENDPOINT}`,
		{
			method: "POST",
			headers: { "Content-Type": "application/json", Accept: "application/json" },
			body: JSON.stringify({ code }),
			signal,
		},
		baseUrl,
	);

	if (!response.ok) {
		throw new OAuthCallbackApiError(response.status, await readErrorCode(response));
	}

	return (await response.json()) as OAuthExchangeResult;
}

export type AuthMeResult = {
	id: string;
	role: AuthUserRole;
	profile_completed: boolean;
};

/** ログイン確立確認。session：Cookie／jwt：Authorizationヘッダで認証される */
export async function fetchAuthMe(signal?: AbortSignal): Promise<AuthMeResult> {
	const baseUrl = getApiBaseUrl();
	const response = await fetchWithAuth(
		`${baseUrl}${AUTH_ME_ENDPOINT}`,
		{
			method: "GET",
			headers: { Accept: "application/json" },
			signal,
		},
		baseUrl,
	);

	if (!response.ok) {
		throw new OAuthCallbackApiError(response.status, await readErrorCode(response));
	}

	return (await response.json()) as AuthMeResult;
}
