import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { OAuthCallbackPage } from "./OAuthCallbackPage";

function renderCallbackPage(hash: string, options?: { strict?: boolean }) {
	window.history.replaceState(null, "", `${ROUTES.OAUTH_CALLBACK}${hash}`);

	const router = createMemoryRouter(
		[
			{ path: ROUTES.OAUTH_CALLBACK, element: <OAuthCallbackPage /> },
			{ path: ROUTES.LOGIN, element: <h1>ログイン画面</h1> },
			{ path: ROUTES.DASHBOARD, element: <h1>ダッシュボード画面</h1> },
			{ path: ROUTES.SETTINGS, element: <h1>アカウント設定画面</h1> },
			{ path: ROUTES.PROJECT_PATTERN, element: <h1>プロジェクト画面</h1> },
		],
		{ initialEntries: [ROUTES.OAUTH_CALLBACK] },
	);
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
	});
	const tree = (
		<QueryClientProvider client={queryClient}>
			<RouterProvider router={router} />
		</QueryClientProvider>
	);

	return render(options?.strict ? <StrictMode>{tree}</StrictMode> : tree);
}

describe("OAuthCallbackPage", () => {
	beforeEach(() => {
		act(() => {
			useAuthStore.getState().reset();
		});
	});

	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
		window.history.replaceState(null, "", "/");
	});

	it("jwtモード正常系：exchangeとme確認後、redirect_toへ遷移する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.includes("/auth/oauth/exchange")) {
				return Promise.resolve({
					ok: true,
					status: 200,
					json: () =>
						Promise.resolve({
							access_token: "token-abc",
							token_type: "bearer",
							expires_in: 900,
							redirect_to: "/projects/1",
						}),
				});
			}
			return Promise.resolve({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: true }),
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=handoff-code&redirect_to=/projects/1");

		expect(await screen.findByRole("heading", { name: "プロジェクト画面" })).toBeInTheDocument();
		expect(useAuthStore.getState().status).toBe("authenticated");
		expect(window.location.hash).toBe("");
	});

	it("jwtモードでprofile_completedがfalseの場合は/settingsへ優先遷移する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.includes("/auth/oauth/exchange")) {
				return Promise.resolve({
					ok: true,
					status: 200,
					json: () =>
						Promise.resolve({
							access_token: "token-abc",
							token_type: "bearer",
							expires_in: 900,
							redirect_to: "/projects/1",
						}),
				});
			}
			return Promise.resolve({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: false }),
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=handoff-code&redirect_to=/projects/1");

		expect(await screen.findByRole("heading", { name: "アカウント設定画面" })).toBeInTheDocument();
	});

	it("jwt交換失敗（400 OAUTH_HANDOFF_INVALID）時は③を表示しhashを除去する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 400,
			json: () => Promise.resolve({ error: { code: "OAUTH_HANDOFF_INVALID" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=expired-code");

		expect(
			await screen.findByText("ログインセッションの有効期限が切れました。もう一度お試しください"),
		).toBeInTheDocument();
		expect(screen.getByRole("alert")).toBeInTheDocument();
		expect(window.location.hash).toBe("");
	});

	it("403 USER_INACTIVEの場合は専用メッセージを表示する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 403,
			json: () => Promise.resolve({ error: { code: "USER_INACTIVE" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=some-code");

		expect(
			await screen.findByText("アカウントが無効化されています。管理者にお問い合わせください"),
		).toBeInTheDocument();
	});

	it("exchangeがネットワークエラーの場合は汎用エラーメッセージを表示する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=some-code");

		expect(await screen.findByText("処理に失敗しました")).toBeInTheDocument();
	});

	it("③表示時に「ログイン画面へ戻る」クリックで/loginへ遷移する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 400,
			json: () => Promise.resolve({ error: { code: "OAUTH_HANDOFF_INVALID" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=expired-code");

		const backLink = await screen.findByRole("link", { name: "ログイン画面へ戻る" });
		fireEvent.click(backLink);

		expect(await screen.findByRole("heading", { name: "ログイン画面" })).toBeInTheDocument();
	});

	it("jwtモードでfragmentにcodeが無い場合は不正なアクセスとして③を表示する", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn();
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("");

		expect(await screen.findByText("不正なアクセスです")).toBeInTheDocument();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("sessionモード正常系：exchangeを呼ばずredirect_toへ遷移する", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: true }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#redirect_to=/projects/1");

		expect(await screen.findByRole("heading", { name: "プロジェクト画面" })).toBeInTheDocument();
		expect(fetchMock).not.toHaveBeenCalledWith(
			expect.stringContaining("/auth/oauth/exchange"),
			expect.anything(),
		);
	});

	it("sessionモードで不正なredirect_toの場合は/dashboardへフォールバックする", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: true }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#redirect_to=//evil.com");

		expect(await screen.findByRole("heading", { name: "ダッシュボード画面" })).toBeInTheDocument();
	});

	it("sessionモードで/auth/meが401の場合は③を表示する", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 401,
			json: () => Promise.resolve({ error: { code: "UNAUTHENTICATED" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#redirect_to=/dashboard");

		expect(await screen.findByText("ログイン処理に失敗しました")).toBeInTheDocument();
	});

	it("StrictMode下でもexchangeは1回しか呼ばれない（二重実行防止）", async () => {
		setAuthAdapterMode("jwt");
		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.includes("/auth/oauth/exchange")) {
				return Promise.resolve({
					ok: true,
					status: 200,
					json: () =>
						Promise.resolve({
							access_token: "token-abc",
							token_type: "bearer",
							expires_in: 900,
							redirect_to: "/projects/1",
						}),
				});
			}
			return Promise.resolve({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: true }),
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		renderCallbackPage("#code=handoff-code&redirect_to=/projects/1", { strict: true });

		await waitFor(() => expect(useAuthStore.getState().status).toBe("authenticated"));

		const exchangeCalls = fetchMock.mock.calls.filter((call: unknown[]) =>
			String(call[0]).includes("/auth/oauth/exchange"),
		);
		expect(exchangeCalls).toHaveLength(1);
	});
});
