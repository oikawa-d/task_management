import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ConfirmDialog from "./ConfirmDialog";

describe("ConfirmDialog", () => {
	it("renders nothing when open is false", () => {
		const { container } = render(
			<ConfirmDialog
				open={false}
				title="タイトル"
				message="メッセージ"
				confirmLabel="確定"
				cancelLabel="キャンセル"
				onConfirm={vi.fn()}
				onCancel={vi.fn()}
			/>,
		);

		expect(container).toBeEmptyDOMElement();
	});

	it("renders the alertdialog with message and error message when open is true", () => {
		render(
			<ConfirmDialog
				open
				title="タイトル"
				message="メッセージ本文"
				confirmLabel="確定"
				cancelLabel="キャンセル"
				errorMessage="エラーが発生しました"
				onConfirm={vi.fn()}
				onCancel={vi.fn()}
			/>,
		);

		expect(screen.getByRole("alertdialog")).toBeInTheDocument();
		expect(screen.getByText("メッセージ本文")).toBeInTheDocument();
		expect(screen.getByText("エラーが発生しました")).toBeInTheDocument();
	});
});
