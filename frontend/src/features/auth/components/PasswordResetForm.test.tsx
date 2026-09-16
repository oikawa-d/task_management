import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { PasswordResetForm } from "./PasswordResetForm";

function response(body: unknown, init: { ok: boolean; status: number; headers?: Record<string, string> }) {
	return { ok: init.ok, status: init.status, headers: new Headers(init.headers), json: vi.fn().mockResolvedValue(body) };
}

function renderForm(props?: { onSuccess?: () => void; onTokenInvalid?: () => void }) {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	}
	return render(<PasswordResetForm token="reset-token" {...props} />, { wrapper: Wrapper });
}

async function fillValidPasswords() {
	fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
	fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Newpass1" } });
	fireEvent.click(screen.getByRole("button", { name: "再設定する" }));
}

describe("PasswordResetForm", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("パスワードと確認が一致しない場合はエラーを表示し送信しない", async () => {
		const fetchMock = vi.fn();
		vi.stubGlobal("fetch", fetchMock);
		renderForm();

		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Different1" } });
		fireEvent.click(screen.getByRole("button", { name: "再設定する" }));

		expect(await screen.findByText("パスワードが一致しません")).toBeInTheDocument();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("文字数・文字種を満たさないパスワードはエラーを表示する", async () => {
		renderForm();
		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "short" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "short" } });
		fireEvent.click(screen.getByRole("button", { name: "再設定する" }));

		expect(await screen.findByText("8文字以上で、2種類以上の文字種を含めてください")).toBeInTheDocument();
	});

	it("204成功時はtoken付きでAPIを呼び出しonSuccessを呼ぶ", async () => {
		const onSuccess = vi.fn();
		const fetchMock = vi.fn().mockResolvedValue(response(undefined, { ok: true, status: 204 }));
		vi.stubGlobal("fetch", fetchMock);
		renderForm({ onSuccess });

		await fillValidPasswords();

		await vi.waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/auth/password/reset",
			expect.objectContaining({
				method: "POST",
				body: JSON.stringify({ token: "reset-token", new_password: "Newpass1", password_confirm: "Newpass1" }),
			}),
		);
	});

	it("400 INVALID_RESET_TOKENはフォームを隠しエラーメッセージのみ表示する", async () => {
		const onTokenInvalid = vi.fn();
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			response({ error: { code: "INVALID_RESET_TOKEN", message: "無効です" } }, { ok: false, status: 400 }),
		));
		renderForm({ onTokenInvalid });

		await fillValidPasswords();

		expect(await screen.findByRole("alert")).toHaveTextContent("リンクの有効期限が切れているか、既に使用済みです");
		expect(screen.queryByLabelText("新しいパスワード")).not.toBeInTheDocument();
		expect(onTokenInvalid).toHaveBeenCalledTimes(1);
	});

	it("429 TOO_MANY_ATTEMPTSは待機時間を案内する", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			response(
				{ error: { code: "TOO_MANY_ATTEMPTS", message: "上限です" } },
				{ ok: false, status: 429, headers: { "Retry-After": "30" } },
			),
		));
		renderForm();

		await fillValidPasswords();

		expect(await screen.findByText(/30秒後に再度お試しください/)).toBeInTheDocument();
		expect(screen.getByLabelText("新しいパスワード")).toBeInTheDocument();
	});
});
