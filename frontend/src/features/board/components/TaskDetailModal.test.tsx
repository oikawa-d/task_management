import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskDetailModal } from "./TaskDetailModal";

const task = {
	id: "task-1",
	project_id: "project-1",
	title: "設計書をレビューする",
	description: "詳細説明",
	status: "in_progress" as const,
	assignee: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 1,
	due_at: "2026-09-10T10:00:00Z",
	comment_count: 1,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

describe("TaskDetailModal", () => {
	it("renders the task detail page layout from the board contract", async () => {
		render(<TaskDetailModal projectId="project-1" taskId="task-1" task={task} onClose={vi.fn()} />);

		expect(await screen.findByRole("dialog", { name: "タスク詳細" })).toBeInTheDocument();
		expect(await screen.findByDisplayValue("設計書をレビューする")).toBeInTheDocument();
		expect(screen.getByDisplayValue("詳細説明")).toBeInTheDocument();
		expect(screen.getByText("コメント一覧・投稿は準備中です。")).toBeInTheDocument();
	});

	it("closes with the button or Escape and restores the previous focus", async () => {
		const onClose = vi.fn();
		const trigger = document.createElement("button");
		document.body.append(trigger);
		trigger.focus();
		const view = render(<TaskDetailModal projectId="project-1" taskId="task-1" task={task} onClose={onClose} />);
		const dialog = await screen.findByRole("dialog", { name: "タスク詳細" });
		await waitFor(() => expect(screen.getByDisplayValue("設計書をレビューする")).toHaveFocus());

		fireEvent.keyDown(dialog, { key: "Escape" });
		expect(onClose).toHaveBeenCalledTimes(1);
		view.unmount();
		expect(trigger).toHaveFocus();
		expect(document.body.style.overflow).toBe("");
		trigger.remove();
	});

	it("shows the modal not-found state when the board has no matching task", async () => {
		render(<TaskDetailModal projectId="project-1" taskId="missing" onClose={vi.fn()} />);

		expect(await screen.findByText("タスクが見つかりません")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "ボードへ戻る" })).toBeInTheDocument();
	});
});
