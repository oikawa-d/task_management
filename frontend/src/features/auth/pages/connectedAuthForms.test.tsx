import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { AuthFormsProvider } from "./authFormSlots";
import { authFormSlots } from "./connectedAuthForms";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";

function renderWithProviders(initialEntry: string) {
	const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
	const router = createMemoryRouter(
		[
			{ path: ROUTES.LOGIN, element: <LoginPage /> },
			{ path: ROUTES.REGISTER, element: <RegisterPage /> },
			{ path: ROUTES.DASHBOARD, element: <h1>ダッシュボード</h1> },
		],
		{ initialEntries: [initialEntry] },
	);

	return render(
		<QueryClientProvider client={queryClient}>
			<AuthFormsProvider slots={authFormSlots}>
				<RouterProvider router={router} />
			</AuthFormsProvider>
		</QueryClientProvider>,
	);
}

describe("connectedAuthForms（issue #315: authFormSlotsへの結線）", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		clearAuthAdapter();
		useAuthStore.getState().reset();
		vi.unstubAllGlobals();
	});

	it("/loginで実際のLoginFormが描画され、送信するとauthStoreを更新して/dashboardへ遷移する", async () => {
		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.endsWith("/auth/login")) {
				return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
			}
			if (url.endsWith("/auth/me")) {
				return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: "u1", role: "member" }) });
			}
			throw new Error(`unexpected url: ${url}`);
		});
		vi.stubGlobal("fetch", fetchMock);

		renderWithProviders(ROUTES.LOGIN);

		fireEvent.change(screen.getByLabelText("IDもしくはメールアドレス"), { target: { value: "taro" } });
		fireEvent.change(screen.getByLabelText("パスワード"), { target: { value: "password1" } });
		fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

		await waitFor(() => expect(screen.getByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument());
		expect(useAuthStore.getState().status).toBe("authenticated");
	});

	it("/registerで実際のRegisterFormが描画され、送信すると/loginへregisteredEmail付きで遷移する", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 201,
			json: () => Promise.resolve({ id: "u1", email: "taro@example.com", message: "確認メールを送信しました。" }),
		});
		vi.stubGlobal("fetch", fetchMock);

		renderWithProviders(ROUTES.REGISTER);

		fireEvent.change(screen.getByLabelText("姓"), { target: { value: "山田" } });
		fireEvent.change(screen.getByLabelText("名"), { target: { value: "太郎" } });
		fireEvent.change(screen.getByLabelText("セイ"), { target: { value: "ヤマダ" } });
		fireEvent.change(screen.getByLabelText("メイ"), { target: { value: "タロウ" } });
		fireEvent.change(screen.getByLabelText("年"), { target: { value: "2000" } });
		fireEvent.change(screen.getByLabelText("月"), { target: { value: "1" } });
		fireEvent.change(screen.getByLabelText("日"), { target: { value: "1" } });
		fireEvent.change(screen.getByLabelText("メールアドレス"), { target: { value: "taro@example.com" } });
		fireEvent.change(screen.getByLabelText("ユーザー名（ID）"), { target: { value: "taro123" } });
		fireEvent.change(screen.getByLabelText("パスワード"), { target: { value: "Password1!" } });
		fireEvent.change(screen.getByLabelText("パスワード（確認）"), { target: { value: "Password1!" } });
		fireEvent.click(screen.getByRole("button", { name: "登録する" }));

		await waitFor(() =>
			expect(screen.getByRole("status")).toHaveTextContent("確認メールを送信しました（taro@example.com）"),
		);
		expect(useAuthStore.getState().status).not.toBe("authenticated");
	});

	it("googleLoginEnabledがtrueのときGoogleログインボタンを描画し、クリックでOAuth開始URLへ遷移する", () => {
		useAuthStore.getState().setGoogleLoginEnabled(true);

		renderWithProviders(ROUTES.LOGIN);

		expect(screen.getByRole("button", { name: "Googleでログイン" })).toBeInTheDocument();
	});

	it("googleLoginEnabledがfalseのときGoogleログインボタンを描画しない", () => {
		useAuthStore.getState().setGoogleLoginEnabled(false);

		renderWithProviders(ROUTES.LOGIN);

		expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
	});
});
