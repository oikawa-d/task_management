import { describe, expect, it } from "vitest";

import { moveTask } from "./useUpdateTaskMutation";
import type { BoardResponse } from "../types";

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
