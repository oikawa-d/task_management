import { afterEach, describe, expect, it, vi } from "vitest";

import {
	deleteComment,
	deleteTask,
	getTask,
	getTaskComments,
	patchComment,
	patchTask,
} from "../lib/api/taskDetail";
import { taskDetailStore } from "./taskDetailStore";

vi.mock("../lib/api/taskDetail", () => ({
	deleteComment: vi.fn(),
	deleteTask: vi.fn(),
	getTask: vi.fn(),
	getTaskComments: vi.fn(),
	patchComment: vi.fn(),
	patchTask: vi.fn(),
}));

const task = {
	id: "task-1",
	project_id: "project-1",
	title: "元のタイトル",
	description: null,
	status: "todo" as const,
	assignee: null,
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 3,
	is_active: true,
	project_is_active: true,
	due_at: null,
	comment_count: 1,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

const comment = {
	id: "comment-1",
	task_id: "task-1",
	body: "元のコメント",
	author: task.created_by,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

function apiError(status: number, code: string) {
	return Object.assign(new Error(code), { status, code });
}

describe("taskDetailStore", () => {
	afterEach(() => {
		vi.clearAllMocks();
		taskDetailStore.reset();
	});

	it("タスク詳細とコメントを同時取得してstateへ反映する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [comment], count: 1 });

		await taskDetailStore.open(task.id);

		expect(taskDetailStore.getSnapshot()).toMatchObject({
			task,
			comments: [comment],
			isLoading: false,
			isCommentsLoading: false,
		});
		expect(getTask).toHaveBeenCalledWith(task.id);
		expect(getTaskComments).toHaveBeenCalledWith(task.id);
	});

	it("open時のtask 404はclose要求を立てずnotFoundのみを立てる", async () => {
		vi.mocked(getTask).mockRejectedValue(apiError(404, "NOT_FOUND"));
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });

		await taskDetailStore.open(task.id);

		expect(taskDetailStore.getSnapshot()).toMatchObject({ notFound: true, closeRequested: false });
	});

	it("open時のcomments 404はtask 404と揃えclose要求を立てずnotFoundのみを立てる", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockRejectedValue(apiError(404, "NOT_FOUND"));

		await taskDetailStore.open(task.id);

		expect(taskDetailStore.getSnapshot()).toMatchObject({ notFound: true, closeRequested: false });
	});

	it("更新時に最新versionを送り、タスクとboard再取得通知を更新する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });
		const updatedTask = { ...task, title: "更新後", version: 4 };
		vi.mocked(patchTask).mockResolvedValue(updatedTask);
		await taskDetailStore.open(task.id);

		await taskDetailStore.updateTask(task.id, { title: "更新後" });

		expect(patchTask).toHaveBeenCalledWith(task.id, { title: "更新後", version: 3 });
		expect(taskDetailStore.getSnapshot()).toMatchObject({ task: updatedTask, boardRefreshToken: 1, isSaving: false });
	});

	it("409 TASK_CONFLICT時に再取得し、競合stateを表示する", async () => {
		vi.mocked(getTask)
			.mockResolvedValueOnce(task)
			.mockResolvedValueOnce({ ...task, title: "他ユーザーの更新", version: 4 });
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });
		vi.mocked(patchTask).mockRejectedValue(apiError(409, "TASK_CONFLICT"));
		await taskDetailStore.open(task.id);

		await taskDetailStore.updateTask(task.id, { title: "自分の更新" });

		expect(getTask).toHaveBeenCalledTimes(2);
		expect(taskDetailStore.getSnapshot()).toMatchObject({
			task: { title: "他ユーザーの更新", version: 4 },
			conflictBannerVisible: true,
			isSaving: false,
		});
	});

	it("通信失敗時は現在値を維持してエラーstateにする", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });
		vi.mocked(patchTask).mockRejectedValue(apiError(503, "SERVICE_UNAVAILABLE"));
		await taskDetailStore.open(task.id);

		await taskDetailStore.updateTask(task.id, { title: "更新" });

		expect(taskDetailStore.getSnapshot()).toMatchObject({
			task,
			error: { status: 503, code: "SERVICE_UNAVAILABLE" },
			isSaving: false,
		});
	});

	it("更新対象が404の場合はclose要求をstateへ記録する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });
		vi.mocked(patchTask).mockRejectedValue(apiError(404, "NOT_FOUND"));
		await taskDetailStore.open(task.id);

		await taskDetailStore.updateTask(task.id, { title: "更新" });

		expect(taskDetailStore.getSnapshot()).toMatchObject({ closeRequested: true, isSaving: false });
	});

	it("コメント更新・削除をstateへ反映する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [comment], count: 1 });
		vi.mocked(patchComment).mockResolvedValue({ ...comment, body: "編集後" });
		vi.mocked(deleteComment).mockResolvedValue();
		await taskDetailStore.open(task.id);

		await taskDetailStore.updateComment(comment.id, "編集後");
		expect(taskDetailStore.getSnapshot().comments[0].body).toBe("編集後");
		await taskDetailStore.removeComment(task.id, comment.id);
		expect(taskDetailStore.getSnapshot().comments).toEqual([]);
		expect(taskDetailStore.getSnapshot().task?.comment_count).toBe(0);
	});

	it("コメント削除の404時はコメント一覧を再取得する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments)
			.mockResolvedValueOnce({ task_id: task.id, items: [comment], count: 1 })
			.mockResolvedValueOnce({ task_id: task.id, items: [], count: 0 });
		vi.mocked(deleteComment).mockRejectedValue(apiError(404, "NOT_FOUND"));
		await taskDetailStore.open(task.id);

		await taskDetailStore.removeComment(task.id, comment.id);

		expect(getTaskComments).toHaveBeenCalledTimes(2);
		expect(taskDetailStore.getSnapshot().comments).toEqual([]);
	});

	it("タスク削除成功時はboard再取得通知とclose要求を更新する", async () => {
		vi.mocked(getTask).mockResolvedValue(task);
		vi.mocked(getTaskComments).mockResolvedValue({ task_id: task.id, items: [], count: 0 });
		vi.mocked(deleteTask).mockResolvedValue();
		await taskDetailStore.open(task.id);

		await taskDetailStore.removeTask(task.id);

		expect(taskDetailStore.getSnapshot()).toMatchObject({ boardRefreshToken: 1, closeRequested: true });
	});
});
