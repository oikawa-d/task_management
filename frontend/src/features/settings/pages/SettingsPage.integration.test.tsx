import "@testing-library/jest-dom/vitest";

import axios, { type AxiosInstance } from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapter } from "../../../api/authAdapter/client";
import { resetApiClient } from "../../../api/client";
import { createAuthAdapter, type AuthMode } from "../../../api/authAdapter";
import { ApiError } from "../../../api/errors";
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

function createMockClient(): AxiosInstance {
	return {
		get: vi.fn(),
		patch: vi.fn(),
		put: vi.fn(),
		post: vi.fn(),
		interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
	} as unknown as AxiosInstance;
}

function renderSettings(client: AxiosInstance, mode: AuthMode, initialEntry: string = ROUTES.SETTINGS) {
	const tokenStore = { getAccessToken: () => "access-token", setAccessToken: vi.fn() };
	const adapter = createAuthAdapter(mode, { httpClient: client, tokenStore });
	setAuthAdapter(adapter);
	act(() => useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" }, authAdapter: adapter }));
	const router = createMemoryRouter(appRoutes, { initialEntries: [initialEntry] });
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	vi.spyOn(axios, "create").mockReturnValue(client);
	vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ unread_count: 0 }) })));
	render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>);
	return { adapter, router };
}

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
	clearAuthAdapter();
	resetApiClient();
	act(() => useAuthStore.getState().reset());
});

describe("設定画面の結合経路", () => {
	it.each(["session", "jwt"] as const)("%s認証でプロフィールを取得して表示する", async (mode) => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: completeProfile });
		renderSettings(client, mode);

		expect(await screen.findByDisplayValue("山田")).toBeInTheDocument();
		expect(client.get).toHaveBeenCalledWith("/users/me");
	});

	it("未認証で設定画面へアクセスするとログインへ遷移する", async () => {
		act(() => useAuthStore.setState({ status: "unauthenticated", user: null }));
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.SETTINGS] });
		render(<QueryClientProvider client={new QueryClient()}><RouterProvider router={router} /></QueryClientProvider>);

		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(router.state.location.pathname).toBe(ROUTES.LOGIN);
	});

	it("プロフィール取得のAPI障害は再試行で復帰できる", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>)
			.mockRejectedValueOnce(new ApiError({ code: "INTERNAL_ERROR", message: "障害", status: 500 }))
			.mockResolvedValueOnce({ data: completeProfile });
		renderSettings(client, "session");

		expect(await screen.findByRole("alert")).toHaveTextContent("設定情報を読み込めませんでした");
		fireEvent.click(screen.getByRole("button", { name: "再試行" }));
		expect(await screen.findByDisplayValue("山田")).toBeInTheDocument();
	});

	it("プロフィール取得の認証失敗は未認証状態にしてログインへ遷移する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockRejectedValue(new ApiError({ code: "UNAUTHENTICATED", message: "ログインが必要です", status: 401 }));
		const { router } = renderSettings(client, "jwt");

		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(router.state.location.pathname).toBe(ROUTES.LOGIN);
		expect(useAuthStore.getState().status).toBe("unauthenticated");
	});

	it("未完了プロフィールを保存するとバナーが消え、成功表示が残る", async () => {
		const client = createMockClient();
		const completedProfile = { ...profile, last_name: "山田", first_name: "太郎", last_name_kana: "ヤマダ", first_name_kana: "タロウ", birth_date: "1990-01-01", profile_completed: true };
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: profile }).mockResolvedValueOnce({ data: completedProfile });
		(client.patch as ReturnType<typeof vi.fn>).mockResolvedValue({ data: completedProfile });
		renderSettings(client, "jwt", `${ROUTES.SETTINGS}?complete_profile=1`);

		expect(await screen.findByText("プロフィールを入力してください")).toBeInTheDocument();
		for (const [label, value] of [["姓", "山田"], ["名", "太郎"], ["姓カナ", "ヤマダ"], ["名カナ", "タロウ"], ["生年月日", "1990-01-01"]]) {
			fireEvent.change(screen.getByLabelText(label), { target: { value } });
		}
		await waitFor(() => expect(screen.getByRole("button", { name: "プロフィールを保存" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "プロフィールを保存" }));

		await waitFor(() => expect(client.patch).toHaveBeenCalledWith("/users/me", completedProfilePayload()));
		await waitFor(() => expect(screen.queryByText("プロフィールを入力してください")).not.toBeInTheDocument());
		expect(screen.getAllByText("プロフィールを更新しました").length).toBeGreaterThan(0);
		expect(useAuthStore.getState().user).toMatchObject({ display_name: "山田 太郎" });
	});

	it("パスワードのvalidationと認証失敗をフォームへ表示する", async () => {
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: completeProfile });
		(client.put as ReturnType<typeof vi.fn>).mockRejectedValue(new ApiError({ code: "INVALID_CREDENTIALS", message: "不正", status: 401 }));
		renderSettings(client, "session");
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
		const client = createMockClient();
		(client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { ...profile, profile_completed: true } });
		(client.put as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 204 });
		(client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 204 });
		renderSettings(client, mode);
		fireEvent.click(await screen.findByRole("tab", { name: "パスワード" }));
		fireEvent.change(screen.getByLabelText("現在のパスワード"), { target: { value: "Oldpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード"), { target: { value: "Newpass1" } });
		fireEvent.change(screen.getByLabelText("新しいパスワード（確認）"), { target: { value: "Newpass1" } });
		await waitFor(() => expect(screen.getByRole("button", { name: "パスワードを変更" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "パスワードを変更" }));

		await waitFor(() => expect(client.put).toHaveBeenCalledWith("/users/me/password", { current_password: "Oldpass1", new_password: "Newpass1", password_confirm: "Newpass1" }));
		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(client.post).toHaveBeenCalledWith("/auth/logout", undefined, expect.anything());
		expect(useAuthStore.getState().status).toBe("unauthenticated");
	});
});

function completedProfilePayload() {
	return { last_name: "山田", first_name: "太郎", last_name_kana: "ヤマダ", first_name_kana: "タロウ", birth_date: "1990-01-01" };
}
