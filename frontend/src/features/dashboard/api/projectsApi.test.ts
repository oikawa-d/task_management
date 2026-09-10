import axios, { type AxiosInstance } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetApiClient } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { createProject, getProjects } from "./projectsApi";
import type { ProjectSummary } from "./types";

function createMockClient(): AxiosInstance {
	return {
		get: vi.fn(),
		post: vi.fn(),
		interceptors: {
			request: { use: vi.fn() },
			response: { use: vi.fn() },
		},
	} as unknown as AxiosInstance;
}

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
		resetApiClient();
	});

	it("getProjects: GET /projects をページング既定値付きで呼び、itemsとmetaを返す", async () => {
		const client = createMockClient();
		const response = { items: [buildProject()], meta: { page: 1, per_page: 20, total: 1, total_pages: 1 } };
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: response });
		vi.spyOn(axios, "create").mockReturnValue(client);

		const result = await getProjects();

		expect(client.get).toHaveBeenCalledWith("/projects", {
			params: { page: 1, per_page: 20, include_inactive: false },
		});
		expect(result).toEqual(response);
	});

	it("getProjects: 5xx応答は共通クライアントのインターセプタが変換したApiErrorのまま伝搬する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockRejectedValue(
			new ApiError({ code: "INTERNAL_ERROR", message: "サーバーエラー", status: 500 }),
		);
		vi.spyOn(axios, "create").mockReturnValue(client);

		await expect(getProjects()).rejects.toMatchObject({ code: "INTERNAL_ERROR", status: 500 });
	});

	it("getProjects: ネットワークエラーもApiErrorのまま伝搬する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockRejectedValue(
			new ApiError({ code: "NETWORK_ERROR", message: "通信に失敗しました", status: null }),
		);
		vi.spyOn(axios, "create").mockReturnValue(client);

		await expect(getProjects()).rejects.toMatchObject({ code: "NETWORK_ERROR", status: null });
	});

	it("createProject: POST /projects へname/descriptionを送信し、作成結果を返す", async () => {
		const client = createMockClient();
		const created = buildProject({ member_count: 1, task_counts: { todo: 0, in_progress: 0, done: 0 } });
		(client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: created });
		vi.spyOn(axios, "create").mockReturnValue(client);

		const result = await createProject({ name: "Cerberus開発", description: "説明" });

		expect(client.post).toHaveBeenCalledWith("/projects", { name: "Cerberus開発", description: "説明" });
		expect(result).toEqual(created);
	});

	it("createProject: 422 VALIDATION_ERRORはfield別detailsを持つApiErrorとして伝搬する", async () => {
		const client = createMockClient();
		(client.post as ReturnType<typeof vi.fn>).mockRejectedValue(
			new ApiError({
				code: "VALIDATION_ERROR",
				message: "入力内容に誤りがあります",
				status: 422,
				details: [{ field: "name", message: "プロジェクト名を1〜100文字で入力してください" }],
			}),
		);
		vi.spyOn(axios, "create").mockReturnValue(client);

		await expect(createProject({ name: "" })).rejects.toMatchObject({
			code: "VALIDATION_ERROR",
			status: 422,
			details: [{ field: "name", message: "プロジェクト名を1〜100文字で入力してください" }],
		});
	});
});
