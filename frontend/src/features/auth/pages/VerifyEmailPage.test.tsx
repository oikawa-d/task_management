import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { VerifyEmailPage } from "./VerifyEmailPage";

function response(body: unknown, init: { ok: boolean; status: number }) {
	return { ok: init.ok, status: init.status, headers: new Headers(), json: vi.fn().mockResolvedValue(body) };
}

function renderPage(hash: string) {
	window.history.replaceState(null, "", `/verify-email${hash}`);
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return render(
		<MemoryRouter>
			<QueryClientProvider client={queryClient}>
				<VerifyEmailPage />
			</QueryClientProvider>
		</MemoryRouter>,
	);
}

describe("VerifyEmailPage", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("有効なtokenを一度だけ検証し、成功表示へ切り替える", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response(undefined, { ok: true, status: 204 }));
		vi.stubGlobal("fetch", fetchMock);

		renderPage("#token=verify-token-123");

		expect(await screen.findByText("メール認証が完了しました")).toBeInTheDocument();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(window.location.hash).toBe("");
	});

	it("無効・期限切れ・使用済みtokenでは失敗表示へ切り替える", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				response({ error: { code: "INVALID_VERIFY_TOKEN", message: "認証リンクが無効です" } }, { ok: false, status: 400 }),
			),
		);

		renderPage("#token=expired-token");

		expect(await screen.findByRole("alert")).toHaveTextContent("リンクの有効期限が切れているか、既に使用済みです");
	});

	it("token欠落時はAPIを呼ばず再送フォームを表示する", async () => {
		const fetchMock = vi.fn();
		vi.stubGlobal("fetch", fetchMock);

		renderPage("");

		expect(await screen.findByText("リンクが不正です")).toBeInTheDocument();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("StrictMode相当の再実行でも検証APIを一度しか呼ばない", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response(undefined, { ok: true, status: 204 }));
		vi.stubGlobal("fetch", fetchMock);
		renderPage("#token=verify-token-123");

		await waitFor(() => expect(screen.getByText("メール認証が完了しました")).toBeInTheDocument());
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
});
