import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KanbanColumn } from "./KanbanColumn";

const task = {
	id: "task-1",
	project_id: "project-1",
	title: "列に表示するタスク",
	description: null,
	status: "in_progress" as const,
	assignee: null,
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 1,
	due_at: null,
	comment_count: 0,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

describe("KanbanColumn", () => {
	it("ステータス名・件数・カードを表示する", () => {
		render(<KanbanColumn status="in_progress" tasks={[task]} onTaskClick={vi.fn()} />);

		expect(screen.getByRole("list", { name: "進行中" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "進行中 1件" })).toBeInTheDocument();
		expect(screen.getByRole("listitem", { name: /列に表示するタスク/ })).toBeInTheDocument();
	});

	it("空の列を空状態として表示する", () => {
		render(<KanbanColumn status="done" tasks={[]} onTaskClick={vi.fn()} />);

		expect(screen.getByRole("list", { name: "完了" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "完了 0件" })).toBeInTheDocument();
		expect(screen.getByText("この列にはタスクがありません")).toBeInTheDocument();
	});
});
