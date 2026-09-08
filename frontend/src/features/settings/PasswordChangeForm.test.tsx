import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PasswordChangeForm } from "./PasswordChangeForm";

describe("PasswordChangeForm", () => {
	it("OAuth専用ユーザーは現在のパスワードを表示せず送信する", async () => {
		const onSubmit = vi.fn().mockResolvedValue(undefined);
		render(<PasswordChangeForm hasPassword={false} onSubmit={onSubmit} />);

		expect(screen.queryByLabelText("現在のパスワード")).not.toBeInTheDocument();
		fireEvent.change(screen.getByLabelText("新しいパスワード"), {
			target: { value: "Newpass1" },
		});
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), {
			target: { value: "Newpass1" },
		});
		fireEvent.click(screen.getByRole("button", { name: "パスワードを変更" }));

		await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
			new_password: "Newpass1",
			password_confirm: "Newpass1",
		}));
		expect(await screen.findByRole("status")).toHaveTextContent("パスワードを変更しました");
	});

	it("現在のパスワードが必要なユーザーは未入力のまま送信できない", async () => {
		const onSubmit = vi.fn();
		render(<PasswordChangeForm hasPassword={true} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("新しいパスワード"), {
			target: { value: "Newpass1" },
		});
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), {
			target: { value: "Newpass1" },
		});

		await waitFor(() => expect(screen.getByRole("button", { name: "パスワードを変更" })).toBeDisabled());
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("新しいパスワードの確認が一致しない場合はエラーを表示する", async () => {
		render(<PasswordChangeForm hasPassword={false} onSubmit={vi.fn()} />);

		fireEvent.change(screen.getByLabelText("新しいパスワード"), {
			target: { value: "Newpass1" },
		});
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), {
			target: { value: "Different1" },
		});

		expect(await screen.findByText("新しいパスワードが一致しません")).toBeInTheDocument();
		await waitFor(() => expect(screen.getByRole("button", { name: "パスワードを変更" })).toBeDisabled());
	});

	it("現在のパスワードが誤っている場合はAPIエラーを表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ code: "INVALID_CREDENTIALS" });
		render(<PasswordChangeForm hasPassword={true} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("現在のパスワード"), { target: { value: "Oldpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Newpass1" } });
		fireEvent.click(screen.getByRole("button", { name: "パスワードを変更" }));

		expect(await screen.findByText("現在のパスワードが正しくありません")).toBeInTheDocument();
	});

	it("OAuth専用ユーザーのINVALID_CREDENTIALSはフォームエラーとして表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ code: "INVALID_CREDENTIALS" });
		render(<PasswordChangeForm hasPassword={false} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Newpass1" } });
		fireEvent.click(screen.getByRole("button", { name: "パスワードを変更" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("再度ログインしてからお試しください");
	});
});
