import { fetchWithAuth } from "../../../api/authAdapter/client";
import type { UnreadCountResponse } from "./types";

/**
 * 未読通知件数取得API `GET /api/notifications/unread-count` を呼び出す。
 *
 * 認証方式の差異は共通APIクライアントへ委譲し、呼び出し側のインターフェースは変更しない。
 */
const DEFAULT_API_BASE_URL = "/api";

/**
 * 未読件数取得APIが異常応答を返した際のエラー。
 * `status` を保持することで、呼び出し側（useUnreadCount）が401時のリトライ抑止など
 * ステータス依存の制御を行えるようにする。
 */
export class UnreadCountFetchError extends Error {
	readonly status: number;

	constructor(status: number) {
		super(`failed to fetch unread count: ${status}`);
		this.name = "UnreadCountFetchError";
		this.status = status;
	}
}

export async function fetchUnreadCount(signal?: AbortSignal): Promise<UnreadCountResponse> {
	const baseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
	const response = await fetchWithAuth(`${baseUrl}/notifications/unread-count`, {
		method: "GET",
		headers: {
			Accept: "application/json",
		},
		signal,
	}, baseUrl);

	if (!response.ok) {
		throw new UnreadCountFetchError(response.status);
	}

	return (await response.json()) as UnreadCountResponse;
}
