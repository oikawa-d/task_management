import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchWithAuth } from "../../../api/authAdapter/client";
import { NOTIFICATION_LIST_DEFAULT_PER_PAGE } from "../config/notificationsConfig";
import { getNotifications } from "./notificationsApi";

vi.mock("../../../api/authAdapter/client", () => ({
	fetchWithAuth: vi.fn(),
}));

const fetchWithAuthMock = vi.mocked(fetchWithAuth);

describe("notificationsApi", () => {
	afterEach(() => {
		vi.resetAllMocks();
	});

	it("getNotifications: 既定per_pageを付け、API契約の通知を画面用データへ変換する", async () => {
		fetchWithAuthMock.mockResolvedValue({
			ok: true,
			json: async () => ({
				items: [
					{
						id: "notification-1",
						type: "due_today_created",
						title: "レビュー期限",
						body: "期限が近いタスクです",
						task: { id: "task-1", project_id: "project-1", title: "設計書レビュー" },
						due_at: "2026-09-11T09:00:00Z",
						read_at: null,
						created_at: "2026-09-10T01:00:00Z",
					},
				],
				meta: { page: 2, total_pages: 3 },
				unread_count: 1,
			}),
		} as Response);

		await expect(getNotifications(2)).resolves.toEqual({
			items: [
				{
					id: "notification-1",
					type: "due_today_created",
					title: "レビュー期限",
					body: "期限が近いタスクです",
					task: { id: "task-1", projectId: "project-1", title: "設計書レビュー" },
					dueAt: "2026-09-11T09:00:00Z",
					readAt: null,
					createdAt: "2026-09-10T01:00:00Z",
				},
			],
			totalPages: 3,
		});
		expect(fetchWithAuthMock).toHaveBeenCalledWith(
			`/api/notifications?page=2&per_page=${NOTIFICATION_LIST_DEFAULT_PER_PAGE}`,
			{
				headers: { Accept: "application/json" },
			},
			"/api",
		);
	});
});
