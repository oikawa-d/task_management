import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RegisterForm } from "./RegisterForm";

function fillValidRegisterForm() {
	fireEvent.change(screen.getByLabelText("姓"), { target: { value: "山田" } });
	fireEvent.change(screen.getByLabelText("名"), { target: { value: "太郎" } });
	fireEvent.change(screen.getByLabelText("セイ"), { target: { value: "ヤマダ" } });
	fireEvent.change(screen.getByLabelText("メイ"), { target: { value: "タロウ" } });
	fireEvent.change(screen.getByLabelText("年"), { target: { value: "1995" } });
	fireEvent.change(screen.getByLabelText("月"), { target: { value: "4" } });
	fireEvent.change(screen.getByLabelText("日"), { target: { value: "1" } });
	fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "taro@example.com" } });
	fireEvent.change(screen.getByLabelText("ユーザー名（ID）"), { target: { value: "taro-1" } });
	fireEvent.change(screen.getByLabelText("パスワード"), { target: { value: "Password1!" } });
	fireEvent.change(screen.getByLabelText("パスワード（確認）"), { target: { value: "Password1!" } });
}

describe("RegisterForm", () => {
	it("正常入力でbirth_dateを整形したペイロードを送信する", async () => {
		const onSubmit = vi.fn().mockResolvedValue(undefined);
		const onSuccess = vi.fn();
		render(<RegisterForm onSubmit={onSubmit} onSuccess={onSuccess} />);

		fillValidRegisterForm();
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		await waitFor(() =>
			expect(onSubmit).toHaveBeenCalledWith(
				expect.objectContaining({
					username: "taro-1",
					email: "taro@example.com",
					birth_date: "1995-04-01",
				}),
			),
		);
		expect(onSuccess).toHaveBeenCalledWith("taro@example.com");
	});

	it("パスワードが1種類のみの文字種だと送信できない", async () => {
		const onSubmit = vi.fn();
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.change(screen.getByLabelText("パスワード"), { target: { value: "aaaaaaaa" } });
		fireEvent.change(screen.getByLabelText("パスワード（確認）"), { target: { value: "aaaaaaaa" } });
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByText(/2種類以上/)).toBeInTheDocument();
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("パスワード確認が一致しないと送信できない", async () => {
		const onSubmit = vi.fn();
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.change(screen.getByLabelText("パスワード（確認）"), { target: { value: "Different1!" } });
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByText("パスワードが一致しません")).toBeInTheDocument();
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("フリガナに漢字を含むと送信できない", async () => {
		const onSubmit = vi.fn();
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.change(screen.getByLabelText("セイ"), { target: { value: "山田" } });
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByText("ひらがな・カタカナ・数字で入力してください")).toBeInTheDocument();
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("409 DUPLICATE_EMAILでメール欄にエラーを表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 409, code: "DUPLICATE_EMAIL" });
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByText("このメールアドレスは既に登録されています")).toBeInTheDocument();
	});

	it("409 DUPLICATE_USERNAMEでユーザー名欄にエラーを表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 409, code: "DUPLICATE_USERNAME" });
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByText("このユーザー名は既に使用されています")).toBeInTheDocument();
	});

	it("422 VALIDATION_ERRORのdetailsを複数フィールドへ分配する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({
			status: 422,
			code: "VALIDATION_ERROR",
			details: [
				{ field: "email", message: "メール形式が不正です" },
				{ field: "username", message: "使用できない文字が含まれています" },
			],
		});
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByText("メール形式が不正です")).toBeInTheDocument();
		expect(await screen.findByText("使用できない文字が含まれています")).toBeInTheDocument();
	});

	it("その他のエラーでは共通バナーを表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 500, code: "INTERNAL_ERROR" });
		render(<RegisterForm onSubmit={onSubmit} />);

		fillValidRegisterForm();
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("登録に失敗しました。しばらくしてから再度お試しください");
	});
});
