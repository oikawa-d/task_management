/**
 * `GET /api/notifications/unread-count` のレスポンス型。
 * 参照: docs/detailed_design/api/notifications/02_get_notifications_unread_count.md §2.2
 */
export interface UnreadCountResponse {
	unread_count: number;
}
