import type { NotificationItemData } from "./types";

/** テスト用の通知データを生成するファクトリ。差分だけ渡せば良いようにする */
export function buildNotification(overrides: Partial<NotificationItemData> = {}): NotificationItemData {
	return {
		id: "notification-1",
		type: "due_soon_batch",
		title: "設計書をレビューする",
		body: "期限が近いタスクです",
		task: { id: "task-1", projectId: "project-1", title: "設計書をレビューする" },
		dueAt: "2026-09-05T09:00:00Z",
		readAt: null,
		createdAt: "2026-09-04T01:00:00Z",
		...overrides,
	};
}
