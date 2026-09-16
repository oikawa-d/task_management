import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskCard } from "./TaskCard";

const task = {
	id: "task-1",
	title: "設計書をレビューする",
	description: null,
	status: "todo" as const,
	assignee: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	project_id: "project-1",
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 3,
	due_at: "2026-09-10T10:00:00Z",
	is_active: true,
	comment_count: 2,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

describe("TaskCard", () => {
	it("タスク情報とドラッグ可能なARIA情報を表示する", () => {
		render(<TaskCard task={task} onClick={vi.fn()} />);

		expect(screen.getByRole("listitem", { name: /設計書をレビューする/ })).toHaveAttribute(
			"aria-roledescription",
			"draggable item",
		);
		expect(screen.getByText(/担当者: 山田 太郎/)).toBeInTheDocument();
		expect(screen.getByText(/期限: 2026年9月10日/)).toBeInTheDocument();
		expect(screen.getByText("コメント: 2件")).toBeInTheDocument();
	});

	it("未割当・期限なしを明示する", () => {
		render(<TaskCard task={{ ...task, assignee: null, due_at: null, comment_count: 0 }} onClick={vi.fn()} />);

		expect(screen.getByText(/担当者: 未割当/)).toBeInTheDocument();
		expect(screen.getByText("期限: なし")).toBeInTheDocument();
		expect(screen.getByText("コメント: 0件")).toBeInTheDocument();
	});

	it("不正な期限をエラー表示する", () => {
		render(<TaskCard task={{ ...task, due_at: "invalid-date" }} onClick={vi.fn()} />);

		expect(screen.getByText("期限: 日付を確認できません")).toBeInTheDocument();
	});
});
