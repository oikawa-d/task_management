import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "./LoginForm";

function fillLoginForm(identifier: string, password: string) {
	fireEvent.change(screen.getByLabelText("IDもしくはメールアドレス"), { target: { value: identifier } });
	fireEvent.change(screen.getByLabelText("パスワード"), { target: { value: password } });
}

describe("LoginForm", () => {
	it("identifier/passwordが未入力だとエラーを表示し送信しない", async () => {
		const onSubmit = vi.fn();
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByText("IDまたはメールアドレスを入力してください")).toBeInTheDocument();
		expect(await screen.findByText("パスワードを入力してください")).toBeInTheDocument();
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("正しい入力でonSubmitへidentifier/passwordを渡す", async () => {
		const onSubmit = vi.fn().mockResolvedValue(undefined);
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("taro", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ identifier: "taro", password: "password1" }));
	});

	it("パスワード表示トグルでtype属性が切り替わる", () => {
		render(<LoginForm onSubmit={vi.fn()} onResendVerification={vi.fn()} />);

		const input = screen.getByLabelText("パスワード") as HTMLInputElement;
		expect(input.type).toBe("password");

		fireEvent.click(screen.getByRole("button", { name: "パスワードを表示/非表示" }));
		expect(input.type).toBe("text");
	});

	it("401 INVALID_CREDENTIALSで統一エラー文言を表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 401, code: "INVALID_CREDENTIALS" });
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("taro", "wrong-password");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("IDまたはパスワードが正しくありません");
	});

	it("403 USER_INACTIVEでアカウント無効化エラーを表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 403, code: "USER_INACTIVE" });
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("taro", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("アカウントが無効化されています。管理者にお問い合わせください");
	});

	it("429 TOO_MANY_ATTEMPTSで待機案内を表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 429, code: "TOO_MANY_ATTEMPTS" });
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("taro", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("試行回数が多いため、しばらく待ってから再度お試しください");
	});

	it("422 VALIDATION_ERRORでdetailsの内容をフィールド直下に表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({
			status: 422,
			code: "VALIDATION_ERROR",
			details: [{ field: "identifier", message: "1文字以上で入力してください" }],
		});
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("t", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByText("1文字以上で入力してください")).toBeInTheDocument();
	});

	it("403 EMAIL_NOT_VERIFIEDで再送ボタンを表示し、クリックで送信済み表示になる", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 403, code: "EMAIL_NOT_VERIFIED" });
		const onResendVerification = vi.fn().mockResolvedValue(undefined);
		render(<LoginForm onSubmit={onSubmit} onResendVerification={onResendVerification} />);

		fillLoginForm("taro@example.com", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		const resendButton = await screen.findByRole("button", { name: "認証メールを再送する" });
		fireEvent.click(resendButton);

		await waitFor(() => expect(onResendVerification).toHaveBeenCalledWith({ email: "taro@example.com" }));
		expect(await screen.findByRole("button", { name: "送信しました" })).toBeInTheDocument();
	});

	it("ユーザー名でのログイン失敗時は再送用メールアドレス入力欄を表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({ status: 403, code: "EMAIL_NOT_VERIFIED" });
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("taro-username", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByLabelText("再送先メールアドレス")).toBeInTheDocument();
	});

	it("ネットワークエラー時は通信失敗メッセージを表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue(new TypeError("network error"));
		render(<LoginForm onSubmit={onSubmit} onResendVerification={vi.fn()} />);

		fillLoginForm("taro", "password1");
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("通信に失敗しました");
	});
});
