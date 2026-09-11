import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { AuthFormsProvider, type AuthFormSlots } from "./authFormSlots";
import { LoginPage } from "./LoginPage";

function renderLoginPage(options: {
	initialEntry?: string;
	state?: unknown;
	slots?: AuthFormSlots;
} = {}) {
	const { initialEntry = ROUTES.LOGIN, state, slots } = options;
	const router = createMemoryRouter(
		[
			{ path: ROUTES.LOGIN, element: <LoginPage /> },
			{ path: ROUTES.DASHBOARD, element: <h1>ダッシュボード</h1> },
		],
		{
			initialEntries: [{ pathname: initialEntry, state }],
		},
	);

	return render(
		<AuthFormsProvider slots={slots}>
			<RouterProvider router={router} />
		</AuthFormsProvider>,
	);
}

describe("LoginPage", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("/loginで表示され、ログインフォームのスロットを描画する", () => {
		renderLoginPage();

		expect(screen.getByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(screen.getByRole("form", { name: "ログインフォーム" })).toBeInTheDocument();
	});

	it("registeredEmailがlocation.stateにある場合、登録直後メッセージを表示する", () => {
		renderLoginPage({ state: { registeredEmail: "a@example.com" } });

		expect(screen.getByRole("status")).toHaveTextContent(
			"確認メールを送信しました（a@example.com）",
		);
	});

	it("registeredEmailが無い場合、登録直後メッセージを表示しない", () => {
		renderLoginPage();

		expect(screen.queryByRole("status")).not.toBeInTheDocument();
	});

	it("loginFormスロットへ接続し、onSuccessで/dashboardへ遷移する", () => {
		const loginForm = vi.fn(({ onSuccess }: { onSuccess: () => void }) => (
			<button type="button" onClick={onSuccess}>
				stub-login-submit
			</button>
		));

		renderLoginPage({ slots: { loginForm } });

		expect(loginForm).toHaveBeenCalledWith(expect.objectContaining({ onSuccess: expect.any(Function) }));
		fireEvent.click(screen.getByRole("button", { name: "stub-login-submit" }));

		expect(screen.getByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument();
	});

	it("googleLoginButtonスロットが無い場合はGoogleログイン導線を表示しない", () => {
		useAuthStore.getState().setGoogleLoginEnabled(true);

		renderLoginPage();

		expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
	});

	it("googleLoginButtonスロットが接続され、google_login_enabled=trueの場合は描画する", () => {
		useAuthStore.getState().setGoogleLoginEnabled(true);
		const googleLoginButton = vi.fn(({ label }: { label: string }) => (
			<button type="button">{label}</button>
		));

		renderLoginPage({ slots: { googleLoginButton } });

		expect(googleLoginButton).toHaveBeenCalledWith({ label: "Googleでログイン" });
		expect(screen.getByRole("button", { name: "Googleでログイン" })).toBeInTheDocument();
	});

	// design doc: docs/detailed_design/screen/01_login.md §14 No.9 "LoginPage hides Google button when disabled"
	it("LoginPage hides Google button when disabled", () => {
		useAuthStore.getState().setGoogleLoginEnabled(false);
		const googleLoginButton = vi.fn(({ label }: { label: string }) => (
			<button type="button">{label}</button>
		));

		renderLoginPage({ slots: { googleLoginButton } });

		expect(googleLoginButton).not.toHaveBeenCalled();
		expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
		expect(screen.queryByText("または")).not.toBeInTheDocument();
	});

	it("新規会員登録とパスワード再設定へのリンクを表示する", () => {
		renderLoginPage();

		expect(screen.getByRole("link", { name: "新規会員登録はこちら" })).toHaveAttribute(
			"href",
			ROUTES.REGISTER,
		);
		expect(screen.getByRole("link", { name: "パスワードを忘れた方はこちら" })).toHaveAttribute(
			"href",
			ROUTES.PASSWORD_FORGOT,
		);
	});
});
