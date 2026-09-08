/**
 * 通知パネル関連のコンポーネントが使う型定義。
 *
 * API連携（未読件数取得・一覧取得・既読化）は別issueで実装される想定のため、
 * ここでは表示に必要な最小限の型のみを定義し、コンポーネントはprops経由で
 * データとコールバックを受け取る疎結合な設計とする。
 */

/** 通知種別（notifications.type のCHECK制約に対応） */
export type NotificationType = "due_soon_batch" | "due_today_created" | "due_today_updated";

/** 通知に紐づくタスク情報。タスクが削除済みの場合は null */
export interface NotificationTaskRef {
	id: string;
	projectId: string;
	title: string;
}

/** 通知1件分のデータ */
export interface NotificationItemData {
	id: string;
	type: NotificationType;
	title: string;
	body: string | null;
	task: NotificationTaskRef | null;
	dueAt: string | null;
	readAt: string | null;
	createdAt: string;
}

/** ページネーション情報 */
export interface NotificationPageInfo {
	page: number;
	totalPages: number;
}
