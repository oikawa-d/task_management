import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommentForm } from "./CommentForm";

describe("CommentForm", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
	});

	it("環境変数VITE_TASK_COMMENT_BODY_MAX_LENGTHが未設定・不正値でも既定の2000文字上限を適用する", () => {
		vi.stubEnv("VITE_TASK_COMMENT_BODY_MAX_LENGTH", "invalid");
		const onSubmit = vi.fn();
		render(<CommentForm onSubmit={onSubmit} />);

		const input = screen.getByLabelText("コメント");
		fireEvent.change(input, { target: { value: "x".repeat(2001) } });
		expect(screen.getByText("コメントは1〜2000文字で入力してください")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "投稿" }));
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("本文が空のとき投稿ボタンを非活性にする", () => {
		render(<CommentForm onSubmit={vi.fn()} maxBodyLength={2000} />);

		const submit = screen.getByRole("button", { name: "投稿" });
		expect(submit).toBeDisabled();
		fireEvent.change(screen.getByLabelText("コメント"), { target: { value: "  " } });
		expect(submit).toBeDisabled();
	});

	it("コメント投稿時に本文をコールバックへ渡して入力欄をクリアする", () => {
		const onSubmit = vi.fn();
		render(<CommentForm onSubmit={onSubmit} maxBodyLength={2000} />);

		const input = screen.getByLabelText("コメント");
		fireEvent.change(input, { target: { value: "  投稿コメント  " } });
		fireEvent.click(screen.getByRole("button", { name: "投稿" }));

		expect(onSubmit).toHaveBeenCalledWith("  投稿コメント  ");
		expect(input).toHaveValue("");
	});

	it("上限超過とAPIエラーを表示し投稿しない", () => {
		const onSubmit = vi.fn();
		render(
			<CommentForm
				onSubmit={onSubmit}
				maxBodyLength={2000}
				error="コメントを投稿できませんでした"
			/>,
		);

		const input = screen.getByLabelText("コメント");
		fireEvent.change(input, { target: { value: "x".repeat(2001) } });
		expect(screen.getByText("コメントは1〜2000文字で入力してください")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "投稿" }));
		expect(onSubmit).not.toHaveBeenCalled();
		expect(screen.getByText("コメントを投稿できませんでした")).toBeInTheDocument();
	});
});
