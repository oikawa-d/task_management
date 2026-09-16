import { fetchWithAuth } from "./authAdapter/client";
import { ApiError, type ApiErrorDetails } from "./errors";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

type ErrorEnvelope = {
	code?: string;
	message?: string;
	details?: ApiErrorDetails;
	request_id?: string | null;
	error?: { code?: string; message?: string; details?: ApiErrorDetails; request_id?: string | null };
};

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
	let response: Response;
	try {
		const headers = new Headers(init.headers);
		headers.set("Accept", "application/json");
		if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
		response = await fetchWithAuth(`${API_BASE_URL}${path}`, {
			...init,
			headers,
		}, API_BASE_URL);
	} catch (error) {
		throw error instanceof ApiError ? error : new ApiError({ code: "NETWORK_ERROR", message: "通信に失敗しました", status: null });
	}
	if (!response.ok) {
		let body: ErrorEnvelope = {};
		try {
			body = (await response.json()) as ErrorEnvelope;
		} catch {
			// エラー本文がJSONでない場合はHTTPステータスだけを保持する。
		}
		throw new ApiError({
			code: body.error?.code ?? body.code ?? "UNKNOWN_ERROR",
			message: body.error?.message ?? body.message ?? `API request failed: ${response.status}`,
			status: response.status,
			details: body.error?.details ?? body.details,
			requestId: body.error?.request_id ?? body.request_id ?? response.headers?.get?.("x-request-id") ?? null,
		});
	}
	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}
