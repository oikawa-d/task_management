import "@testing-library/jest-dom/vitest";

import { act, renderHook } from "@testing-library/react";
import type { RenderHookResult } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getTask, getTaskComments } from "../../../lib/api/taskDetail";
import { taskDetailStore } from "../../../stores/taskDetailStore";
import { useTaskDetail } from "./useTaskDetail";

vi.hoisted(() => {
	(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

vi.mock("../../../lib/api/taskDetail", () => ({
	getTask: vi.fn(),
	getTaskComments: vi.fn(),
}));

const task = {
	id: "task-1",
	project_id: "project-1",
	title: "タスク",
	description: null,
	status: "todo" as const,
	assignee: null,
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 1,
	is_active: true,
	project_is_active: true,
	due_at: null,
	comment_count: 0,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

describe("useTaskDetail", () => {
	afterEach(() => {
		vi.clearAllMocks();
		taskDetailStore.reset();
	});

	it("taskIdが変わったときにopenして取得結果を返す", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });

		let result: { current: ReturnType<typeof useTaskDetail> } | undefined;
		let view: RenderHookResult<ReturnType<typeof useTaskDetail>, void> | undefined;
		await act(async () => {
			view = renderHook(() => useTaskDetail(task.id));
			result = view.result;
			await new Promise((resolve) => setTimeout(resolve, 0));
		});
		expect(result?.current.task).toEqual(task);
		expect(result?.current.isLoading).toBe(false);
		view?.unmount();
	});

	it("closeRequested時にonCloseを呼び、同じ要求を消費する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });
		const onClose = vi.fn();
		let result: { current: ReturnType<typeof useTaskDetail> } | undefined;
		let view: RenderHookResult<ReturnType<typeof useTaskDetail>, void> | undefined;
		await act(async () => {
			view = renderHook(() => useTaskDetail(task.id, { onClose }));
			result = view.result;
			await new Promise((resolve) => setTimeout(resolve, 0));
		});
		expect(result?.current.task).toEqual(task);
		act(() => taskDetailStore.requestClose());

		await act(async () => {
			await new Promise((resolve) => setTimeout(resolve, 0));
		});
		expect(onClose).toHaveBeenCalledTimes(1);
		expect(taskDetailStore.getSnapshot().closeRequested).toBe(false);
		view?.unmount();
	});
});
