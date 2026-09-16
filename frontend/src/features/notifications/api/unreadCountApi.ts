import { requestJson } from "../../../api/http";
import type { UnreadCountResponse } from "./types";

/**
 * 未読通知件数取得API `GET /api/notifications/unread-count` を呼び出す。
 *
 * 認証方式の差異は共通APIクライアントへ委譲し、呼び出し側のインターフェースは変更しない。
 */
/**
 * 未読件数取得APIが異常応答を返した際のエラー。
 * `status` を保持することで、呼び出し側（useUnreadCount）が401時のリトライ抑止など
 * ステータス依存の制御を行えるようにする。
 */
export { ApiError as UnreadCountFetchError } from "../../../api/errors";

export async function fetchUnreadCount(signal?: AbortSignal): Promise<UnreadCountResponse> {
	return requestJson<UnreadCountResponse>("/notifications/unread-count", { method: "GET", signal });
}
