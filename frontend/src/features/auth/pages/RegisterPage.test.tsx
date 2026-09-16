import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { AuthFormsProvider, type AuthFormSlots } from "./authFormSlots";
import { RegisterPage } from "./RegisterPage";

function renderRegisterPage(slots?: AuthFormSlots) {
	const router = createMemoryRouter(
		[
			{ path: ROUTES.REGISTER, element: <RegisterPage /> },
			{
				path: ROUTES.LOGIN,
				element: <LoginRouteProbe />,
			},
		],
		{ initialEntries: [ROUTES.REGISTER] },
	);

	return render(
		<AuthFormsProvider slots={slots}>
			<RouterProvider router={router} />
		</AuthFormsProvider>,
	);
}

function LoginRouteProbe() {
	return <h1>ログイン画面（登録後の遷移先）</h1>;
}

describe("RegisterPage", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("/registerで表示され、会員登録フォームのスロットを描画する", () => {
		renderRegisterPage();

		expect(screen.getByRole("heading", { name: "Cerberus 会員登録" })).toBeInTheDocument();
		expect(screen.getByRole("form", { name: "会員登録フォーム" })).toBeInTheDocument();
	});

	it("registerFormスロットへ接続し、onSuccessで/loginへ遷移する", () => {
		const registerForm = vi.fn(({ onSuccess }: { onSuccess: (email: string) => void }) => (
			<button type="button" onClick={() => onSuccess("new@example.com")}>
				stub-register-submit
			</button>
		));

		renderRegisterPage({ registerForm });

		expect(registerForm).toHaveBeenCalledWith(
			expect.objectContaining({ onSuccess: expect.any(Function) }),
		);
		fireEvent.click(screen.getByRole("button", { name: "stub-register-submit" }));

		expect(screen.getByRole("heading", { name: "ログイン画面（登録後の遷移先）" })).toBeInTheDocument();
	});

	it("googleLoginButtonスロットが無い場合はGoogleログイン導線を表示しない", () => {
		useAuthStore.getState().setGoogleLoginEnabled(true);

		renderRegisterPage();

		expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
	});

	it("googleLoginButtonスロットが接続された場合は描画する", () => {
		useAuthStore.getState().setGoogleLoginEnabled(true);
		const googleLoginButton = vi.fn(({ label }: { label: string }) => (
			<button type="button">{label}</button>
		));

		renderRegisterPage({ googleLoginButton });

		expect(googleLoginButton).toHaveBeenCalledWith({ label: "Googleで新規登録" });
		expect(screen.getByRole("button", { name: "Googleで新規登録" })).toBeInTheDocument();
	});

	// design doc: docs/detailed_design/screen/02_register.md §14 No.10 "RegisterPage hides Google button when disabled"
	it("RegisterPage hides Google button when disabled", () => {
		useAuthStore.getState().setGoogleLoginEnabled(false);
		const googleLoginButton = vi.fn(({ label }: { label: string }) => (
			<button type="button">{label}</button>
		));

		renderRegisterPage({ googleLoginButton });

		expect(googleLoginButton).not.toHaveBeenCalled();
		expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
		expect(screen.queryByText("または")).not.toBeInTheDocument();
	});

	it("ログイン画面へのリンクを表示する", () => {
		renderRegisterPage();

		expect(screen.getByRole("link", { name: "既にアカウントをお持ちの方はこちら" })).toHaveAttribute(
			"href",
			ROUTES.LOGIN,
		);
	});
});
