import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { PasswordForgotForm } from "./PasswordForgotForm";

function response(body: unknown, init: { ok: boolean; status: number; headers?: Record<string, string> }) {
	return { ok: init.ok, status: init.status, headers: new Headers(init.headers), json: vi.fn().mockResolvedValue(body) };
}

function renderForm(onSent?: () => void) {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	}
	return render(<PasswordForgotForm onSent={onSent} />, { wrapper: Wrapper });
}

describe("PasswordForgotForm", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("不正な形式のメールアドレスは送信できない", async () => {
		renderForm();
		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "invalid" } });
		expect(await screen.findByText("メールアドレスの形式が正しくありません")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "送信" })).toBeDisabled();
	});

	it("202受信後は固定メッセージを表示し、入力欄を再表示しない", async () => {
		const onSent = vi.fn();
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ message: "ok" }, { ok: true, status: 202 })));
		renderForm(onSent);

		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "user@example.com" } });
		fireEvent.click(screen.getByRole("button", { name: "送信" }));

		expect(await screen.findByRole("status")).toHaveTextContent("パスワード再設定用のメールを送信しました");
		expect(onSent).toHaveBeenCalledTimes(1);
		expect(screen.queryByLabelText("メールアドレス")).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "送信" })).not.toBeInTheDocument();
	});

	it("送信中は二重送信を防ぐため送信ボタンが非活性になる", async () => {
		let resolveFetch: (value: unknown) => void = () => {};
		const pending = new Promise((resolve) => {
			resolveFetch = resolve;
		});
		vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
		renderForm();

		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "user@example.com" } });
		fireEvent.click(screen.getByRole("button", { name: "送信" }));

		await waitFor(() => expect(screen.getByRole("button")).toBeDisabled());
		resolveFetch(response({ message: "ok" }, { ok: true, status: 202 }));
	});

	it("429 TOO_MANY_ATTEMPTSはRetry-Afterを案内し、完了画面には遷移しない", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			response(
				{ error: { code: "TOO_MANY_ATTEMPTS", message: "上限です" } },
				{ ok: false, status: 429, headers: { "Retry-After": "60" } },
			),
		));
		renderForm();

		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "user@example.com" } });
		fireEvent.click(screen.getByRole("button", { name: "送信" }));

		expect(await screen.findByRole("alert")).toHaveTextContent("60秒後に再度お試しください");
		expect(screen.getByLabelText("メールアドレス")).toBeInTheDocument();
	});
});
