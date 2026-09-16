import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { createProject, getCalendarTasks, getProjects } from "./projectsApi";
import type { ProjectSummary } from "./types";

function buildProject(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
	return {
		id: "project-1",
		name: "Cerberus開発",
		description: "学習用タスク管理システムの開発",
		owner: { id: "user-1", username: "taro", display_name: "山田 太郎" },
		member_count: 3,
		task_counts: { todo: 4, in_progress: 2, done: 7 },
		is_owner: true,
		is_active: true,
		start_at: null,
		end_at: null,
		created_at: "2026-09-01T00:00:00Z",
		...overrides,
	};
}

describe("projectsApi", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	function mockResponse(data: unknown, status = 200): Response {
		return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
	}

	it("getProjects: GET /projects をページング既定値付きで呼び、itemsとmetaを返す", async () => {
		const response = { items: [buildProject()], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } };
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(mockResponse(response));
		vi.stubGlobal("fetch", fetchMock);

		const result = await getProjects();

		expect(fetchMock).toHaveBeenCalledWith("/api/projects?page=1&per_page=20&include_inactive=false", expect.any(Object));
		expect(result).toEqual(response);
	});

	it("getProjects: 5xx応答は共通クライアントのインターセプタが変換したApiErrorのまま伝搬する", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(mockResponse({ error: { code: "INTERNAL_ERROR", message: "サーバーエラー" } }, 500));
		vi.stubGlobal("fetch", fetchMock);

		await expect(getProjects()).rejects.toMatchObject({ code: "INTERNAL_ERROR", status: 500 });
	});

	it("getProjects: ネットワークエラーもApiErrorのまま伝搬する", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockRejectedValue(new TypeError("network"));
		vi.stubGlobal("fetch", fetchMock);

		await expect(getProjects()).rejects.toMatchObject({ code: "NETWORK_ERROR", status: null });
	});

	it("createProject: POST /projects へname/descriptionを送信し、作成結果を返す", async () => {
		const created = buildProject({ member_count: 1, task_counts: { todo: 0, in_progress: 0, done: 0 } });
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(mockResponse(created));
		vi.stubGlobal("fetch", fetchMock);

		const result = await createProject({ name: "Cerberus開発", description: "説明" });

		expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Cerberus開発", description: "説明" }) }));
		expect(result).toEqual(created);
	});

	it("createProject: 422 VALIDATION_ERRORはfield別detailsを持つApiErrorとして伝搬する", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(mockResponse({ error: { code: "VALIDATION_ERROR", message: "入力内容に誤りがあります", details: [{ field: "name", message: "プロジェクト名を1〜100文字で入力してください" }] } }, 422));
		vi.stubGlobal("fetch", fetchMock);

		await expect(createProject({ name: "" })).rejects.toMatchObject({
			code: "VALIDATION_ERROR",
			status: 422,
			details: [{ field: "name", message: "プロジェクト名を1〜100文字で入力してください" }],
		});
	});

	it("getCalendarTasks: 日付範囲とscopeを指定してタスク配列を返す", async () => {
		const tasks = [{ id: "task-1", project_id: null, title: "期限", due_at: "2026-09-10T00:00:00Z", due_date: "2026-09-10", status: "todo" as const }];
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(mockResponse(tasks));
		vi.stubGlobal("fetch", fetchMock);

		await expect(getCalendarTasks({ from: "2026-09-01", to: "2026-09-30", scope: "me" })).resolves.toEqual(tasks);
		expect(fetchMock).toHaveBeenCalledWith("/api/tasks/calendar?from=2026-09-01&to=2026-09-30&scope=me", expect.any(Object));
	});
});
