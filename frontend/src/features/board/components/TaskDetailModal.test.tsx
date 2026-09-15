import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTaskDetail } from "../../task-detail/hooks/useTaskDetail";
import { useProjectMembers } from "../hooks/useProjectMembers";
import { TaskDetailModal } from "./TaskDetailModal";

vi.mock("../../task-detail/hooks/useTaskDetail", () => ({ useTaskDetail: vi.fn() }));
vi.mock("../hooks/useProjectMembers", () => ({ useProjectMembers: vi.fn() }));

const task = {
	id: "task-1",
	title: "設計書をレビューする",
	description: "詳細説明",
	status: "in_progress" as const,
	assignee: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	project_id: "project-1",
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 1,
	due_at: "2026-09-10T10:00:00Z",
	is_active: true,
	comment_count: 1,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

describe("TaskDetailModal", () => {
	beforeEach(() => {
		vi.mocked(useProjectMembers).mockReturnValue({ members: [], isLoading: false, error: null });
		vi.mocked(useTaskDetail).mockReturnValue({
			task: { ...task, project_is_active: true },
			taskId: task.id,
			comments: [],
			isLoading: false,
			isCommentsLoading: false,
			isSaving: false,
			error: null,
			commentsError: null,
			notFound: false,
			conflictBannerVisible: false,
			closeRequested: false,
			boardRefreshToken: 0,
			updateTask: vi.fn(),
			addComment: vi.fn(),
			updateComment: vi.fn(),
			removeComment: vi.fn(),
			removeTask: vi.fn(),
			refresh: vi.fn(),
		});
	});

	it("renders the task detail page layout from the board contract", async () => {
		render(<TaskDetailModal projectId="project-1" taskId="task-1" onClose={vi.fn()} />);

		expect(await screen.findByRole("dialog", { name: "タスク詳細" })).toBeInTheDocument();
		expect(await screen.findByDisplayValue("設計書をレビューする")).toBeInTheDocument();
		expect(screen.getByDisplayValue("詳細説明")).toBeInTheDocument();
		expect(screen.getByText("コメントはありません")).toBeInTheDocument();
	});

	it("closes with the button or Escape and restores the previous focus", async () => {
		const onClose = vi.fn();
		const trigger = document.createElement("button");
		document.body.append(trigger);
		trigger.focus();
		const view = render(<TaskDetailModal projectId="project-1" taskId="task-1" onClose={onClose} />);
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
		vi.mocked(useTaskDetail).mockReturnValue({
			task: null,
			taskId: "missing",
			comments: [],
			isLoading: false,
			isCommentsLoading: false,
			isSaving: false,
			error: null,
			commentsError: null,
			notFound: true,
			conflictBannerVisible: false,
			closeRequested: false,
			boardRefreshToken: 0,
			updateTask: vi.fn(),
			addComment: vi.fn(),
			updateComment: vi.fn(),
			removeComment: vi.fn(),
			removeTask: vi.fn(),
			refresh: vi.fn(),
		});
		render(<TaskDetailModal projectId="project-1" taskId="missing" onClose={vi.fn()} />);

		expect(await screen.findByText("タスクが見つかりません")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "ボードへ戻る" })).toBeInTheDocument();
	});
});
