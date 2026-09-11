import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter } from "../../../api/authAdapter/client";
import { moveTask, useUpdateTaskMutation } from "./useUpdateTaskMutation";
import type { BoardResponse } from "../types";

function jsonResponse(status: number, data: unknown, ok = true) {
	return Promise.resolve({ ok, status, json: () => Promise.resolve(data) });
}

function buildBoard(): BoardResponse {
	return {
		project_id: "project-1",
		project_is_active: true,
		columns: {
			todo: [
				{
					id: "task-1",
					project_id: "project-1",
					title: "移動対象",
					description: null,
					status: "todo",
					assignee: null,
					position: 0,
					version: 1,
					due_at: null,
					is_active: true,
					created_by: { id: "user-1", username: "taro", display_name: "太郎" },
					comment_count: 0,
					created_at: "2026-09-01T00:00:00Z",
					updated_at: "2026-09-01T00:00:00Z",
				},
			],
			in_progress: [],
			done: [],
		},
	};
}

function createWrapper(queryClient: QueryClient) {
	return function Wrapper({ children }: { children: React.ReactNode }) {
		return React.createElement(QueryClientProvider, { client: queryClient }, children);
	};
}

describe("useUpdateTaskMutation", () => {
	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("onMutateが呼ばれた時点でキャッシュを楽観的にmoveTask結果へ更新する", async () => {
		const board = buildBoard();
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
		queryClient.setQueryData(["board", "project-1"], board);

		let resolvePatch!: (value: unknown) => void;
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ auth_mode: "session" }) })
			.mockImplementationOnce(() => new Promise((resolve) => (resolvePatch = resolve)));
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useUpdateTaskMutation("project-1"), { wrapper: createWrapper(queryClient) });

		result.current.mutate({ taskId: "task-1", status: "in_progress", position: 0, version: 1 });

		await waitFor(() => {
			const cached = queryClient.getQueryData<BoardResponse>(["board", "project-1"]);
			expect(cached).toEqual(moveTask(board, { taskId: "task-1", status: "in_progress", position: 0, version: 1 }));
		});

		resolvePatch(await jsonResponse(200, board.columns.todo[0]));
		await waitFor(() => expect(result.current.isSuccess || result.current.isError).toBe(true));
	});

	it("onErrorがTASK_CONFLICT以外の失敗時に楽観更新前の状態へロールバックする", async () => {
		const board = buildBoard();
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
		queryClient.setQueryData(["board", "project-1"], board);

		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ auth_mode: "session" }) })
			.mockResolvedValueOnce({ ok: false, status: 500, json: () => Promise.resolve({ error: { code: "INTERNAL_ERROR" } }) });
		vi.stubGlobal("fetch", fetchMock);

		const onFailure = vi.fn();
		const { result } = renderHook(() => useUpdateTaskMutation("project-1", undefined, onFailure), {
			wrapper: createWrapper(queryClient),
		});

		result.current.mutate({ taskId: "task-1", status: "in_progress", position: 0, version: 1 });

		await waitFor(() => expect(result.current.isError).toBe(true));

		expect(queryClient.getQueryData<BoardResponse>(["board", "project-1"])).toEqual(board);
		expect(onFailure).toHaveBeenCalledTimes(1);
	});

	it("409 TASK_CONFLICT応答時はonConflictを呼び、boardクエリを再取得対象にする", async () => {
		const board = buildBoard();
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
		queryClient.setQueryData(["board", "project-1"], board);
		const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ auth_mode: "session" }) })
			.mockResolvedValueOnce({ ok: false, status: 409, json: () => Promise.resolve({ error: { code: "TASK_CONFLICT" } }) });
		vi.stubGlobal("fetch", fetchMock);

		const onConflict = vi.fn();
		const { result } = renderHook(() => useUpdateTaskMutation("project-1", onConflict), {
			wrapper: createWrapper(queryClient),
		});

		result.current.mutate({ taskId: "task-1", status: "in_progress", position: 0, version: 1 });

		await waitFor(() => expect(result.current.isError).toBe(true));

		expect(onConflict).toHaveBeenCalledTimes(1);
		expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["board", "project-1"] });
	});
});

describe("moveTask", () => {
	it("楽観更新で元のキャッシュを変更せず、statusとpositionを再計算する", () => {
		const board: BoardResponse = {
			project_id: "project-1",
			project_is_active: true,
			columns: {
				todo: [{ id: "task-1", project_id: "project-1", title: "移動", description: null, status: "todo", assignee: null, position: 0, version: 1, due_at: null, is_active: true, created_by: { id: "user-1", username: "taro", display_name: "太郎" }, comment_count: 0, created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" }],
				in_progress: [{ id: "task-2", project_id: "project-1", title: "既存", description: null, status: "in_progress", assignee: null, position: 0, version: 2, due_at: null, is_active: true, created_by: { id: "user-1", username: "taro", display_name: "太郎" }, comment_count: 0, created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" }],
				done: [],
			},
		};

		const updated = moveTask(board, { taskId: "task-1", status: "in_progress", position: 1, version: 1 });

		expect(board.columns.todo).toHaveLength(1);
		expect(board.columns.todo[0].status).toBe("todo");
		expect(updated.columns.todo).toHaveLength(0);
		expect(updated.columns.in_progress.map((task) => [task.id, task.position])).toEqual([["task-2", 0], ["task-1", 1]]);
	});
});
