import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createAuthAdapter } from "../../../api/authAdapter";
import { clearAuthAdapter, setAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { authTokenStore, useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { AuthFormsProvider } from "./authFormSlots";
import { authFormSlots } from "./connectedAuthForms";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";

/**
 * issue #431: ログイン・会員登録画面のphase close要件（親phase #146）を、
 * 画面・form・authStore・認証API境界を通した結合テストで検証する。
 * design doc: docs/detailed_design/screen/01_login.md §14, 02_register.md §14
 *
 * connectedAuthForms.test.tsx（正常系・スロット結線）に対し、本ファイルは
 * ・認証失敗（401/403/429/409/422）で誤ってログイン済みにならないこと
 * ・API/外部I/O障害時に誤ってログイン済みにならないこと
 * ・jwtモードでの認証state
 * を補う。
 */

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

function jsonResponse(status: number, body: unknown) {
	return Promise.resolve({
		ok: status < 400,
		status,
		headers: new Headers(),
		json: () => Promise.resolve(body),
	});
}

function fillLoginForm(identifier: string, password: string) {
	fireEvent.change(screen.getByLabelText("IDもしくはメールアドレス"), { target: { value: identifier } });
	fireEvent.change(screen.getByLabelText("パスワード"), { target: { value: password } });
}

function fillRegisterForm(overrides: Partial<Record<string, string>> = {}) {
	const values: Record<string, string> = {
		姓: "山田",
		名: "太郎",
		セイ: "ヤマダ",
		メイ: "タロウ",
		年: "2000",
		月: "1",
		日: "1",
		メールアドレス: "taro@example.com",
		"ユーザー名（ID）": "taro123",
		パスワード: "Password1!",
		"パスワード（確認）": "Password1!",
		...overrides,
	};
	Object.entries(values).forEach(([label, value]) => {
		fireEvent.change(screen.getByLabelText(label), { target: { value } });
	});
}

describe("認証画面 結合テスト（issue #431: phase close要件検証）", () => {
	afterEach(() => {
		clearAuthAdapter();
		useAuthStore.getState().reset();
		vi.unstubAllGlobals();
	});

	describe("ログイン（session方式）の失敗系", () => {
		beforeEach(() => {
			setAuthAdapterMode("session");
		});

		it("401 INVALID_CREDENTIALSの場合、authStoreはunauthenticatedのままエラー表示し/dashboardへ遷移しない", async () => {
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/login")) {
					return jsonResponse(401, { error: { code: "INVALID_CREDENTIALS", message: "IDまたはパスワードが正しくありません" } });
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.LOGIN);
			fillLoginForm("taro", "wrong-password");
			fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

			expect(await screen.findByRole("alert")).toHaveTextContent("IDまたはパスワードが正しくありません");
			expect(screen.getByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
			expect(screen.queryByRole("heading", { name: "ダッシュボード" })).not.toBeInTheDocument();
			expect(useAuthStore.getState().status).not.toBe("authenticated");
		});

		// design doc: docs/detailed_design/screen/01_login.md §11 429 TOO_MANY_ATTEMPTS
		it("429 TOO_MANY_ATTEMPTSの場合、待機案内を表示し認証済みにしない", async () => {
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/login")) {
					return jsonResponse(429, { error: { code: "TOO_MANY_ATTEMPTS", message: "試行回数が多すぎます" } });
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.LOGIN);
			fillLoginForm("taro", "password1");
			fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

			expect(await screen.findByRole("alert")).toHaveTextContent(
				"試行回数が多いため、しばらく待ってから再度お試しください",
			);
			expect(useAuthStore.getState().status).not.toBe("authenticated");
		});

		it("認証API呼び出しが例外（ネットワーク障害）を送出した場合、誤ってログイン済みにならない", async () => {
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/login")) {
					return Promise.reject(new TypeError("Failed to fetch"));
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.LOGIN);
			fillLoginForm("taro", "password1");
			fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

			expect(await screen.findByRole("alert")).toBeInTheDocument();
			expect(screen.queryByRole("heading", { name: "ダッシュボード" })).not.toBeInTheDocument();
			expect(useAuthStore.getState().status).not.toBe("authenticated");
		});
	});

	describe("ログイン（jwt方式）", () => {
		function setupJwtAdapter() {
			const adapter = createAuthAdapter("jwt", { tokenStore: authTokenStore });
			setAuthAdapter(adapter);
			useAuthStore.getState().setAuthAdapter(adapter);
		}

		it("成功時はaccess_tokenを共有TokenStoreへ保持し/dashboardへ遷移する", async () => {
			setupJwtAdapter();
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/login")) {
					return jsonResponse(200, { access_token: "jwt-token-123", token_type: "bearer" });
				}
				if (url.endsWith("/auth/me")) {
					return jsonResponse(200, { id: "u1", role: "member" });
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.LOGIN);
			fillLoginForm("taro", "password1");
			fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

			await waitFor(() => expect(screen.getByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument());
			expect(useAuthStore.getState().status).toBe("authenticated");
			expect(authTokenStore.getAccessToken()).toBe("jwt-token-123");
		});

		it("401 INVALID_CREDENTIALSの場合、accessTokenを保持せずunauthenticatedのままにする", async () => {
			setupJwtAdapter();
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/login")) {
					return jsonResponse(401, { error: { code: "INVALID_CREDENTIALS", message: "IDまたはパスワードが正しくありません" } });
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.LOGIN);
			fillLoginForm("taro", "wrong-password");
			fireEvent.click(screen.getByRole("button", { name: "ログイン" }));

			expect(await screen.findByRole("alert")).toHaveTextContent("IDまたはパスワードが正しくありません");
			expect(useAuthStore.getState().status).not.toBe("authenticated");
			expect(authTokenStore.getAccessToken()).toBeNull();
		});
	});

	describe("会員登録の失敗系", () => {
		beforeEach(() => {
			setAuthAdapterMode("session");
		});

		it("409 DUPLICATE_EMAILの場合、該当フィールドにエラー表示し/loginへ遷移しない", async () => {
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/register")) {
					return jsonResponse(409, { error: { code: "DUPLICATE_EMAIL", message: "既に登録されています" } });
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.REGISTER);
			fillRegisterForm();
			fireEvent.click(screen.getByRole("button", { name: "登録する" }));

			expect(await screen.findByText("このメールアドレスは既に登録されています")).toBeInTheDocument();
			expect(screen.getByRole("heading", { name: "Cerberus 会員登録" })).toBeInTheDocument();
			expect(useAuthStore.getState().status).not.toBe("authenticated");
		});

		it("422 VALIDATION_ERRORの場合、detailsの各フィールドへエラーを分配する", async () => {
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/register")) {
					return jsonResponse(422, {
						error: {
							code: "VALIDATION_ERROR",
							message: "入力内容を確認してください",
							details: [{ field: "username", message: "このユーザー名は使用できません" }],
						},
					});
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.REGISTER);
			fillRegisterForm();
			fireEvent.click(screen.getByRole("button", { name: "登録する" }));

			expect(await screen.findByText("このユーザー名は使用できません")).toBeInTheDocument();
			expect(useAuthStore.getState().status).not.toBe("authenticated");
		});

		it("APIが例外を送出（ネットワーク障害）した場合、誤って登録完了扱いにせず/loginへ遷移しない", async () => {
			const fetchMock = vi.fn().mockImplementation((url: string) => {
				if (url.endsWith("/auth/register")) {
					return Promise.reject(new TypeError("Failed to fetch"));
				}
				throw new Error(`unexpected url: ${url}`);
			});
			vi.stubGlobal("fetch", fetchMock);

			renderWithProviders(ROUTES.REGISTER);
			fillRegisterForm();
			fireEvent.click(screen.getByRole("button", { name: "登録する" }));

			expect(await screen.findByRole("alert")).toBeInTheDocument();
			expect(screen.getByRole("heading", { name: "Cerberus 会員登録" })).toBeInTheDocument();
			expect(useAuthStore.getState().status).not.toBe("authenticated");
		});
	});
});
