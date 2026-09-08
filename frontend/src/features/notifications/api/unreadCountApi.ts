import type { UnreadCountResponse } from "./types";

/**
 * 未読通知件数取得API `GET /api/notifications/unread-count` を呼び出す。
 *
 * NOTE: 共通APIクライアント（axiosインスタンス + AuthAdapter、docs/basic_design/05_frontend.md §6）は
 * 別task（#178 通知API等と並行実装中）のため、本taskの責務(state管理/ポーリング)としては
 * 疎結合な最小実装として fetch を直接使用する。共通クライアントのマージ後は本関数の内部実装のみを
 * 差し替え、呼び出し側（useUnreadCount）のインターフェースは変更しない想定。
 */
const DEFAULT_API_BASE_URL = "/api";

export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
	const baseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
	const response = await fetch(`${baseUrl}/notifications/unread-count`, {
		method: "GET",
		credentials: "include",
		headers: {
			Accept: "application/json",
		},
	});

	if (!response.ok) {
		throw new Error(`failed to fetch unread count: ${response.status}`);
	}

	return (await response.json()) as UnreadCountResponse;
}
