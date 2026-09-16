import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommentList, type TaskComment } from "./CommentList";

const comments: TaskComment[] = [
	{
		id: "comment-1",
		task_id: "task-1",
		body: "最初のコメント",
		author: { id: "user-1", username: "taro", display_name: "山田 太郎" },
		created_at: "2026-09-01T10:00:00Z",
		updated_at: "2026-09-01T10:00:00Z",
	},
	{
		id: "comment-2",
		task_id: "task-1",
		body: "別のコメント",
		author: { id: "user-2", username: "hanako", display_name: "佐藤 花子" },
		created_at: "2026-09-01T11:00:00Z",
		updated_at: "2026-09-01T11:00:00Z",
	},
];

describe("CommentList", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
	});

	it("環境変数VITE_TASK_COMMENT_BODY_MAX_LENGTHが未設定・不正値でも既定の2000文字上限を適用する", () => {
		vi.stubEnv("VITE_TASK_COMMENT_BODY_MAX_LENGTH", "0");
		const onEdit = vi.fn();
		render(
			<CommentList
				comments={comments}
				currentUserId="user-1"
				currentUserRole="member"
				onEdit={onEdit}
			/>,
		);

		fireEvent.click(screen.getByRole("button", { name: "編集" }));
		const editor = screen.getByDisplayValue("最初のコメント");
		fireEvent.change(editor, { target: { value: "x".repeat(2001) } });
		fireEvent.click(screen.getByRole("button", { name: "保存" }));
		expect(screen.getByText("コメントは1〜2000文字で入力してください")).toBeInTheDocument();
		expect(onEdit).not.toHaveBeenCalled();
	});

	it("空状態とエラー状態を表示する", () => {
		const { rerender } = render(<CommentList comments={[]} currentUserId="user-1" currentUserRole="member" />);
		expect(screen.getByText("コメントはありません")).toBeInTheDocument();

		rerender(
			<CommentList
				comments={[]}
				currentUserId="user-1"
				currentUserRole="member"
				error="コメントを読み込めませんでした"
			/>,
		);
		expect(screen.getByRole("alert")).toHaveTextContent("コメントを読み込めませんでした");
	});

	it("投稿者本人だけが編集・削除でき、削除は確認後に通知する", () => {
		const onEdit = vi.fn();
		const onDelete = vi.fn();
		vi.spyOn(window, "confirm").mockReturnValue(true);
		render(
			<CommentList
				comments={comments}
				currentUserId="user-1"
				currentUserRole="member"
				onEdit={onEdit}
				onDelete={onDelete}
				maxBodyLength={2000}
			/>,
		);

		expect(screen.getAllByRole("button", { name: "編集" })).toHaveLength(1);
		expect(screen.getAllByRole("button", { name: "削除" })).toHaveLength(1);
		fireEvent.click(screen.getByRole("button", { name: "編集" }));
		const editor = screen.getByDisplayValue("最初のコメント");
		fireEvent.change(editor, { target: { value: "編集後のコメント" } });
		fireEvent.click(screen.getByRole("button", { name: "保存" }));
		expect(onEdit).toHaveBeenCalledWith("comment-1", "編集後のコメント");

		fireEvent.click(screen.getByRole("button", { name: "削除" }));
		expect(onDelete).toHaveBeenCalledWith("comment-1");
		vi.mocked(window.confirm).mockReturnValue(false);
		fireEvent.click(screen.getByRole("button", { name: "削除" }));
		expect(onDelete).toHaveBeenCalledTimes(1);
	});

	it("adminは他人のコメントも編集・削除できる", () => {
		render(
			<CommentList
				comments={[comments[1]]}
				currentUserId="admin-1"
				currentUserRole="admin"
				onEdit={vi.fn()}
				onDelete={vi.fn()}
			/>,
		);

		expect(screen.getByRole("button", { name: "編集" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "削除" })).toBeInTheDocument();
	});
});
