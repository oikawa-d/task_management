import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter } from "../../api/authAdapter/client";
import { BoardApiError, getProjectTasks, updateTask } from "./api";

describe("board API", () => {
	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("共通認証クライアント経由でボードを取得する", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ auth_mode: "session" }),
			})
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ columns: { todo: [], in_progress: [], done: [] } }),
			});
		vi.stubGlobal("fetch", fetchMock);

		await expect(getProjectTasks("project-1")).resolves.toEqual({
			columns: { todo: [], in_progress: [], done: [] },
		});

		expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project-1/tasks", expect.any(Object));
	});

	it("タスク移動のPATCHでContent-Typeを保持し、エラー契約のcodeを取り出す", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ auth_mode: "session" }),
			})
			.mockResolvedValueOnce({
				ok: false,
				status: 409,
				json: () => Promise.resolve({ error: { code: "TASK_CONFLICT" } }),
			});
		vi.stubGlobal("fetch", fetchMock);

		await expect(updateTask("task-1", { version: 2, status: "done", position: 0 })).rejects.toEqual(
			expect.objectContaining<Partial<BoardApiError>>({ status: 409, code: "TASK_CONFLICT" }),
		);
		expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/tasks/task-1", expect.objectContaining({ method: "PATCH" }));
		const requestHeaders = fetchMock.mock.calls[1][1].headers as Headers;
		expect(requestHeaders.get("accept")).toBe("application/json");
		expect(requestHeaders.get("content-type")).toBe("application/json");
	});
});
