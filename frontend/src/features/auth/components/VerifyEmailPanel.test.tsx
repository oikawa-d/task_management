import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { VerifyEmailPanel } from "./VerifyEmailPanel";

function response(body: unknown, init: { ok: boolean; status: number }) {
	return { ok: init.ok, status: init.status, headers: new Headers(), json: vi.fn().mockResolvedValue(body) };
}

function renderPanel(phase: "noToken" | "verifying" | "success" | "error", onRedirectNow?: () => void, errorMessage?: string) {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	}
	return render(<VerifyEmailPanel phase={phase} errorMessage={errorMessage} onRedirectNow={onRedirectNow} />, { wrapper: Wrapper });
}

describe("VerifyEmailPanel", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("verifying状態では検証中メッセージのみ表示する", () => {
		renderPanel("verifying");
		expect(screen.getByRole("status")).toHaveTextContent("メールアドレスを確認中です");
		expect(screen.queryByLabelText("メールアドレス")).not.toBeInTheDocument();
	});

	it("success状態では即時遷移リンククリックでonRedirectNowを呼ぶ", () => {
		const onRedirectNow = vi.fn();
		renderPanel("success", onRedirectNow);

		expect(screen.getByText("メール認証が完了しました")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "今すぐ移動する" }));
		expect(onRedirectNow).toHaveBeenCalledTimes(1);
	});

	it("error状態では失敗メッセージと再送フォームを表示する", () => {
		renderPanel("error");
		expect(screen.getByRole("alert")).toHaveTextContent("リンクの有効期限が切れているか、既に使用済みです");
		expect(screen.getByLabelText("メールアドレス")).toBeInTheDocument();
	});

	it("errorMessage指定時は共通エラーを表示する", () => {
		renderPanel("error", undefined, "エラーが発生しました。しばらくしてから再度お試しください");
		expect(screen.getByRole("alert")).toHaveTextContent("エラーが発生しました。しばらくしてから再度お試しください");
	});

	it("noToken状態ではリンク不正メッセージと再送フォームを表示する（APIは呼ばれない）", () => {
		const fetchMock = vi.fn();
		vi.stubGlobal("fetch", fetchMock);
		renderPanel("noToken");

		expect(screen.getByText("リンクが不正です")).toBeInTheDocument();
		expect(screen.getByLabelText("メールアドレス")).toBeInTheDocument();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("再送ボタン押下で常に送信済みメッセージを表示する（存在有無を問わない）", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ message: "ok" }, { ok: true, status: 202 })));
		renderPanel("error");

		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "user@example.com" } });
		fireEvent.click(screen.getByRole("button", { name: "認証メールを再送する" }));

		expect(await screen.findByText(/送信しました/)).toBeInTheDocument();
	});

	it("不正な形式のメールアドレスは再送ボタンを非活性にする", async () => {
		renderPanel("error");
		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "invalid" } });

		expect(await screen.findByText("有効なメールアドレスを入力してください")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "認証メールを再送する" })).toBeDisabled();
	});
});
