import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KanbanBoard, resolveTaskMove } from "./KanbanBoard";
import type { BoardColumns } from "../types";

const task = (id: string, status: "todo" | "in_progress" | "done", position: number) => ({
	id,
	project_id: "project-1",
	title: `${id}のタスク`,
	description: null,
	status,
	assignee: null,
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position,
	version: 1,
	due_at: null,
	comment_count: 0,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
});

const columns: BoardColumns = {
	todo: [task("task-1", "todo", 0), task("task-2", "todo", 1)],
	in_progress: [],
	done: [],
};

describe("KanbanBoard", () => {
	it("3列を描画し、エラーを通知領域に表示する", () => {
		render(<KanbanBoard columns={columns} onTaskMove={vi.fn()} errorMessage="最新状態を取得できません" />);

		expect(screen.getByRole("list", { name: "未着手" })).toBeInTheDocument();
		expect(screen.getByRole("list", { name: "進行中" })).toBeInTheDocument();
		expect(screen.getByRole("list", { name: "完了" })).toBeInTheDocument();
		expect(screen.getByRole("alert")).toHaveTextContent("最新状態を取得できません");
	});

	it("列間移動のstatusと末尾positionを解決する", () => {
		const result = resolveTaskMove(
			{ active: { id: "task-1" }, over: { id: "column:done", data: { current: { type: "column", status: "done" } } } },
			columns,
		);

		expect(result).toEqual({ taskId: "task-1", status: "done", position: 0, version: 1 });
	});

	it("カードのEnterで詳細操作を呼び出せる", () => {
		const onTaskClick = vi.fn();
		render(<KanbanBoard columns={columns} onTaskMove={vi.fn()} onTaskClick={onTaskClick} />);

		const card = screen.getByRole("listitem", { name: /task-1のタスク/ });
		card.focus();
		fireEvent.keyDown(card, { key: "Enter", code: "Enter" });

		expect(onTaskClick).toHaveBeenCalledWith("task-1");
	});

	it("カードをSpaceでキーボードドラッグ状態にできる", () => {
		render(<KanbanBoard columns={columns} onTaskMove={vi.fn()} />);

		const card = screen.getByRole("listitem", { name: /task-1のタスク/ });
		card.focus();
		fireEvent.keyDown(card, { key: " ", code: "Space" });

		expect(screen.getByText(/task-1のタスクをドラッグ中です/)).toBeInTheDocument();
	});

	it("同じ位置・列外・不正な対象は移動通知しない", () => {
		const samePosition = resolveTaskMove(
			{ active: { id: "task-1" }, over: { id: "task-1", data: { current: { type: "task", status: "todo" } } } },
			columns,
		);
		const outside = resolveTaskMove({ active: { id: "task-1" }, over: null }, columns);
		const invalid = resolveTaskMove(
			{ active: { id: "missing" }, over: { id: "column:done", data: { current: { type: "column", status: "done" } } } },
			columns,
		);

		expect(samePosition).toBeNull();
		expect(outside).toBeNull();
		expect(invalid).toBeNull();
	});

	it("同一列の並べ替えは対象カードのpositionを返す", () => {
		const result = resolveTaskMove(
			{ active: { id: "task-2" }, over: { id: "task-1", data: { current: { type: "task", status: "todo" } } } },
			columns,
		);

		expect(result).toEqual({ taskId: "task-2", status: "todo", position: 0, version: 1 });
	});

	it("不正な列IDは移動通知しない", () => {
		const result = resolveTaskMove(
			{ active: { id: "task-1" }, over: { id: "column:unknown", data: { current: { type: "column" } } } },
			columns,
		);

		expect(result).toBeNull();
	});
});
