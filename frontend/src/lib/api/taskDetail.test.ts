import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskDetailApiError, deleteComment, getTask, patchTask } from "./taskDetail";

function response(body: unknown, init: { ok: boolean; status: number }) {
	return {
		...init,
		json: vi.fn().mockResolvedValue(body),
	};
}

describe("taskDetail API", () => {
	afterEach(() => vi.unstubAllGlobals());

	it("GETでCookieを送信し、タスク詳細を返す", async () => {
		const task = { id: "task-1" };
		const fetchMock = vi.fn().mockResolvedValue(response(task, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await expect(getTask(task.id)).resolves.toEqual(task);
		expect(fetchMock).toHaveBeenCalledWith("/api/tasks/task-1", expect.objectContaining({ credentials: "include" }));
	});

	it("PATCHにversionを含むJSONを送信する", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response({ id: "task-1" }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await patchTask("task-1", { title: "更新", version: 2 });

		expect(fetchMock).toHaveBeenCalledWith(
			"/api/tasks/task-1",
			expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "更新", version: 2 }) }),
		);
	});

	it("204削除はJSONを読まずに成功する", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response(undefined, { ok: true, status: 204 }));
		vi.stubGlobal("fetch", fetchMock);

		await expect(deleteComment("comment-1")).resolves.toBeUndefined();
	});

	it("エラー応答のcodeをTaskDetailApiErrorとして返す", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ code: "TASK_CONFLICT" }, { ok: false, status: 409 })));

		await expect(getTask("task-1")).rejects.toEqual(expect.objectContaining({
			constructor: TaskDetailApiError,
			status: 409,
			code: "TASK_CONFLICT",
		}));
	});
});
