import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskEditForm, type TaskEditFormValues } from "./TaskEditForm";

const task: TaskEditFormValues = {
	title: "設計書をレビューする",
	description: "レビュー内容",
	assignee_id: "user-1",
	due_at: "2026-09-10T10:00",
	status: "in_progress",
};

const members = [
	{ id: "user-1", display_name: "山田 太郎", is_active: true },
	{ id: "user-3", display_name: "鈴木 一郎", is_active: true },
	{ id: "user-2", display_name: "佐藤 花子", is_active: false },
];

describe("TaskEditForm", () => {
	it("タスクの値を表示し、タイトル変更はblur時に通知する", () => {
		const onUpdate = vi.fn();
		render(<TaskEditForm task={task} members={members} onUpdate={onUpdate} />);

		const title = screen.getByLabelText("タイトル");
		expect(title).toHaveValue(task.title);
		fireEvent.blur(title);
		expect(onUpdate).not.toHaveBeenCalled();

		fireEvent.change(title, { target: { value: "更新後のタイトル" } });
		fireEvent.blur(title);
		expect(onUpdate).toHaveBeenCalledWith("title", "更新後のタイトル");
	});

	it("説明・担当者・期限・ステータスの変更を適切な値で通知する", () => {
		const onUpdate = vi.fn();
		render(<TaskEditForm task={task} members={members} onUpdate={onUpdate} />);

		const description = screen.getByLabelText("説明");
		fireEvent.change(description, { target: { value: "新しい説明" } });
		fireEvent.blur(description);
		fireEvent.change(screen.getByLabelText("担当者"), { target: { value: "user-3" } });
		fireEvent.change(screen.getByLabelText("期限"), { target: { value: "2026-09-11T12:30" } });
		fireEvent.change(screen.getByLabelText("ステータス"), { target: { value: "done" } });

		expect(onUpdate).toHaveBeenNthCalledWith(1, "description", "新しい説明");
		expect(onUpdate).toHaveBeenNthCalledWith(2, "assignee_id", "user-3");
		expect(onUpdate).toHaveBeenNthCalledWith(3, "due_at", "2026-09-11T12:30");
		expect(onUpdate).toHaveBeenNthCalledWith(4, "status", "done");
		expect(onUpdate).toHaveBeenCalledTimes(4);
	});

	it("無効な担当者を選択できず、タイトルと説明の境界値を検証する", () => {
		const onUpdate = vi.fn();
		render(<TaskEditForm task={task} members={members} onUpdate={onUpdate} />);

		expect(screen.getByRole("option", { name: "佐藤 花子（無効）" })).toBeDisabled();
		const title = screen.getByLabelText("タイトル");
		fireEvent.change(title, { target: { value: "" } });
		fireEvent.blur(title);
		expect(screen.getByText("タイトルは1〜150文字で入力してください")).toBeInTheDocument();

		fireEvent.change(screen.getByLabelText("説明"), { target: { value: "x".repeat(2001) } });
		fireEvent.blur(screen.getByLabelText("説明"));
		expect(screen.getByText("説明は2000文字以内で入力してください")).toBeInTheDocument();
		expect(onUpdate).not.toHaveBeenCalled();
	});
});
