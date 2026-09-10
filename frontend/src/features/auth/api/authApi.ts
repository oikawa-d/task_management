import { fetchWithAuth } from "../../../api/authAdapter/client";
import type { ApiFieldError } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

/**
 * メール認証・パスワードリセット系APIの共通エラー。
 * レスポンス形式（docs/basic_design/04_api.md §4.1）: `{ error: { code, message, details, request_id } }`
 */
export class AuthApiError extends Error {
	readonly status: number;
	readonly code: string | undefined;
	readonly details: ApiFieldError[] | null;
	/** 429 TOO_MANY_ATTEMPTS時のRetry-After（秒）。ヘッダ欠落時はnull */
	readonly retryAfterSeconds: number | null;

	constructor(status: number, code?: string, message?: string, details: ApiFieldError[] | null = null, retryAfterSeconds: number | null = null) {
		super(message ?? code ?? "API_ERROR");
		this.name = "AuthApiError";
		this.status = status;
		this.code = code;
		this.details = details;
		this.retryAfterSeconds = retryAfterSeconds;
	}
}

interface ErrorEnvelope {
	error?: {
		code?: string;
		message?: string;
		details?: ApiFieldError[] | null;
	};
}

function parseRetryAfterSeconds(response: Response): number | null {
	const value = response.headers.get("Retry-After");
	if (!value) return null;
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}

async function request<T = void>(path: string, init?: RequestInit): Promise<T> {
	const headers = new Headers(init?.headers);
	headers.set("Accept", "application/json");
	if (init?.body) headers.set("Content-Type", "application/json");

	let response: Response;
	try {
		response = await fetchWithAuth(`${API_BASE_URL}${path}`, { ...init, headers }, API_BASE_URL);
	} catch {
		throw new AuthApiError(0, "NETWORK_ERROR", "通信に失敗しました");
	}

	if (!response.ok) {
		let body: ErrorEnvelope = {};
		try {
			body = (await response.json()) as ErrorEnvelope;
		} catch {
			body = {};
		}
		throw new AuthApiError(
			response.status,
			body.error?.code,
			body.error?.message,
			body.error?.details ?? null,
			parseRetryAfterSeconds(response),
		);
	}

	if (response.status === 204 || response.status === 202) {
		return undefined as T;
	}
	return (await response.json()) as T;
}

/** POST /api/auth/password/forgot（docs/detailed_design/api/auth/09_post_auth_password_forgot.md） */
export function requestPasswordReset(email: string): Promise<void> {
	return request("/auth/password/forgot", {
		method: "POST",
		body: JSON.stringify({ email }),
	});
}

/** POST /api/auth/password/reset（docs/detailed_design/api/auth/10_post_auth_password_reset.md） */
export function resetPassword(payload: { token: string; new_password: string; password_confirm: string }): Promise<void> {
	return request("/auth/password/reset", {
		method: "POST",
		body: JSON.stringify(payload),
	});
}

/** POST /api/auth/verify-email/resend（docs/detailed_design/api/auth/08_post_auth_verify_email_resend.md） */
export function resendVerification(email: string): Promise<void> {
	return request("/auth/verify-email/resend", {
		method: "POST",
		body: JSON.stringify({ email }),
	});
}

/** POST /api/auth/verify-email（docs/detailed_design/api/auth/07_post_auth_verify_email.md） */
export function verifyEmail(token: string): Promise<void> {
	return request("/auth/verify-email", {
		method: "POST",
		body: JSON.stringify({ token }),
	});
}
