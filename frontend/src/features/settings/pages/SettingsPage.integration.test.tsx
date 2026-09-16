import "@testing-library/jest-dom/vitest";

import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapter } from "../../../api/authAdapter/client";
import { getApiClient, resetApiClient } from "../../../api/client";
import { createAuthAdapter, type AuthMode } from "../../../api/authAdapter";
import { useAuthStore } from "../../../auth/authStore";
import { appRoutes } from "../../../router";
import { ROUTES } from "../../../routes";

const profile = {
	id: "user-1",
	username: "taro",
	email: "taro@example.com",
	last_name: null,
	first_name: null,
	last_name_kana: null,
	first_name_kana: null,
	birth_date: null,
	profile_completed: false,
	role: "member" as const,
	has_password: true,
	oauth_providers: [],
};

const completeProfile = {
	...profile,
	last_name: "山田",
	first_name: "太郎",
	last_name_kana: "ヤマダ",
	first_name_kana: "タロウ",
	birth_date: "1990-01-01",
	profile_completed: true,
};

type TestPlan =
	| { data: unknown; status?: number }
	| { error: { code: string; message: string; status: number } };

function createTestClient(plans: TestPlan[]): { client: AxiosInstance; requests: InternalAxiosRequestConfig[] } {
	const requests: InternalAxiosRequestConfig[] = [];
	const client = axios.create({
		adapter: async (config) => {
			requests.push(config);
			const plan = plans.shift();
			if (!plan) {
				throw new Error(`Unexpected request: ${config.method} ${config.url}`);
			}
			if ("error" in plan) {
				const { code, message, status } = plan.error;
				const response = {
					config,
					data: { error: { code, message, details: null, request_id: null } },
					headers: {},
					status,
					statusText: "Error",
				};
				throw new AxiosError(message, code, config, undefined, response);
			}
			return {
				config,
				data: plan.data,
				headers: {},
				status: plan.status ?? 200,
				statusText: "OK",
			};
		},
	});
	return { client, requests };
}

function renderSettings(mode: AuthMode, plans: TestPlan[], initialEntry: string = ROUTES.SETTINGS) {
	const testClient = createTestClient(plans);
	const tokenStore = { getAccessToken: () => "access-token", setAccessToken: vi.fn() };
	const adapter = createAuthAdapter(mode, { httpClient: testClient.client, tokenStore });
	setAuthAdapter(adapter);
	act(() => useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" }, authAdapter: adapter }));
	const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	vi.spyOn(axios, "create").mockReturnValue(testClient.client);
	resetApiClient();
	getApiClient({ authAdapter: adapter });
	document.cookie = "cerberus_csrf=csrf-token";
	vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = new URL(String(input), "http://localhost");
		if (url.pathname.endsWith("/notifications/unread-count")) {
			return new Response(JSON.stringify({ unread_count: 0 }), { status: 200 });
		}
		try {
			const result = await testClient.client.request({
				method: init?.method ?? "GET",
				url: url.pathname.replace(/^\/api/, ""),
				data: init?.body,
				headers: Object.fromEntries(new Headers(init?.headers).entries()),
				withCredentials: init?.credentials === "include",
			});
			return new Response(result.data === undefined ? undefined : JSON.stringify(result.data), { status: result.status });
		} catch (error) {
			if (!(error instanceof AxiosError) || !error.response) throw error;
			return new Response(JSON.stringify(error.response.data), { status: error.response.status });
		}
	}));
	render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
	return { adapter, router, ...testClient };
}

function findRequest(requests: InternalAxiosRequestConfig[], method: string, url: string) {
	return requests.find((request) => request.method === method && request.url === url);
}

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
	sessionStorage.clear();
	clearAuthAdapter();
	resetApiClient();
	act(() => useAuthStore.getState().reset());
});

	describe("設定画面の結合経路", () => {
	it.each(["session", "jwt"] as const)("%s認証でプロフィールを取得して表示する", async (mode) => {
		const { requests } = renderSettings(mode, [{ data: completeProfile }]);

		expect(await screen.findByDisplayValue("山田")).toBeInTheDocument();
		const request = findRequest(requests, "get", "/users/me");
		expect(request).toBeDefined();
		if (mode === "jwt") {
			expect(request?.headers.get("Authorization")).toBe("Bearer access-token");
		} else {
			expect(request?.withCredentials).toBe(true);
			expect(request?.headers.get("X-CSRF-Token")).toBeUndefined();
		}
	});

	it("未認証で設定画面へアクセスするとログインへ遷移する", async () => {
		act(() => useAuthStore.setState({ status: "unauthenticated", user: null }));
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.SETTINGS] });
		render(<QueryClientProvider client={new QueryClient()}><RouterProvider router={router} /></QueryClientProvider>);

		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(router.state.location.pathname).toBe(ROUTES.LOGIN);
	});

	it("プロフィール取得のAPI障害は再試行で復帰できる", async () => {
		renderSettings("session", [
			{ error: { code: "INTERNAL_ERROR", message: "障害", status: 500 } },
			{ data: completeProfile },
		]);

		expect(await screen.findByRole("alert")).toHaveTextContent("設定情報を読み込めませんでした");
		fireEvent.click(screen.getByRole("button", { name: "再試行" }));
		expect(await screen.findByDisplayValue("山田")).toBeInTheDocument();
	});

	it("プロフィール取得の認証失敗は未認証状態にしてログインへ遷移する", async () => {
		const { router } = renderSettings("jwt", [
			{ error: { code: "UNAUTHENTICATED", message: "ログインが必要です", status: 401 } },
			{ error: { code: "TOKEN_INVALID", message: "失効", status: 401 } },
		]);

		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(router.state.location.pathname).toBe(ROUTES.LOGIN);
		expect(useAuthStore.getState().status).toBe("unauthenticated");
	});

	it("未完了プロフィールを保存するとバナーが消え、成功表示が残る", async () => {
		const completedProfile = { ...profile, last_name: "山田", first_name: "太郎", last_name_kana: "ヤマダ", first_name_kana: "タロウ", birth_date: "1990-01-01", profile_completed: true };
		const { requests } = renderSettings(
			"jwt",
			[{ data: profile }, { data: completedProfile }, { data: completedProfile }],
			`${ROUTES.SETTINGS}?complete_profile=1`,
		);

		expect(await screen.findByText("プロフィールを入力してください")).toBeInTheDocument();
		for (const [label, value] of [["姓", "山田"], ["名", "太郎"], ["姓カナ", "ヤマダ"], ["名カナ", "タロウ"], ["生年月日", "1990-01-01"]]) {
			fireEvent.change(screen.getByLabelText(label), { target: { value } });
		}
		await waitFor(() => expect(screen.getByRole("button", { name: "プロフィールを保存" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "プロフィールを保存" }));

		await waitFor(() => expect(findRequest(requests, "patch", "/users/me")).toBeDefined());
		const patchRequest = findRequest(requests, "patch", "/users/me");
		expect(JSON.parse(String(patchRequest?.data))).toEqual(completedProfilePayload());
		expect(patchRequest?.headers.get("Authorization")).toBe("Bearer access-token");
		await waitFor(() => expect(screen.queryByText("プロフィールを入力してください")).not.toBeInTheDocument());
		expect(screen.getAllByText("プロフィールを更新しました").length).toBeGreaterThan(0);
		expect(useAuthStore.getState().user).toMatchObject({ display_name: "山田 太郎" });
	});

	it("パスワードのvalidationと認証失敗をフォームへ表示する", async () => {
		renderSettings("session", [
			{ data: completeProfile },
			{ error: { code: "INVALID_CREDENTIALS", message: "不正", status: 401 } },
		]);
		fireEvent.click(await screen.findByRole("tab", { name: "パスワード" }));
		fireEvent.change(screen.getByLabelText("現在のパスワード"), { target: { value: "Oldpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "weak" } });
		expect(await screen.findByText("8文字以上で、2種類以上の文字種を含めてください")).toBeInTheDocument();
		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Newpass1" } });
		await waitFor(() => expect(screen.getByRole("button", { name: "パスワードを変更" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "パスワードを変更" }));

		expect(await screen.findByText("現在のパスワードが正しくありません")).toBeInTheDocument();
	});

	it.each(["session", "jwt"] as const)("%s認証でパスワード変更成功後にlogoutしてログインへ遷移する", async (mode) => {
		const { requests } = renderSettings(mode, [
			{ data: { ...profile, profile_completed: true } },
			{ data: undefined, status: 204 },
			{ data: undefined, status: 204 },
		]);
		fireEvent.click(await screen.findByRole("tab", { name: "パスワード" }));
		fireEvent.change(screen.getByLabelText("現在のパスワード"), { target: { value: "Oldpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Newpass1" } });
		await waitFor(() => expect(screen.getByRole("button", { name: "パスワードを変更" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "パスワードを変更" }));

		await waitFor(() => expect(findRequest(requests, "put", "/users/me/password")).toBeDefined());
		const passwordRequest = findRequest(requests, "put", "/users/me/password");
		expect(JSON.parse(String(passwordRequest?.data))).toEqual({ current_password: "Oldpass1", new_password: "Newpass1", password_confirm: "Newpass1" });
		if (mode === "session") {
			expect(passwordRequest?.withCredentials).toBe(true);
			expect(passwordRequest?.headers.get("X-CSRF-Token")).toBe("csrf-token");
		} else {
			expect(passwordRequest?.headers.get("Authorization")).toBe("Bearer access-token");
		}
		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(await screen.findByRole("status")).toHaveTextContent("パスワードを変更しました。再度ログインしてください");
		expect(findRequest(requests, "post", "/auth/logout")).toBeDefined();
		expect(findRequest(requests, "post", "/auth/logout")?.withCredentials).toBe(true);
		expect(useAuthStore.getState().status).toBe("unauthenticated");
	});
});

function completedProfilePayload() {
	return { last_name: "山田", first_name: "太郎", last_name_kana: "ヤマダ", first_name_kana: "タロウ", birth_date: "1990-01-01" };
}
