import "@testing-library/jest-dom/vitest";

import axios, { type AxiosInstance } from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { AuthAdapter } from "./api/authAdapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetApiClient } from "./api/client";
import { useAuthStore } from "./auth/authStore";
import { appRoutes } from "./router";
import styles from "./layouts/AuthLayout.module.css";
import { ROUTES } from "./routes";

describe("アプリケーションルート", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
			const body = String(input).endsWith("/auth/config") ? { auth_mode: "session" } : { unread_count: 0 };
			return { ok: true, status: 200, json: async () => body };
		}));
	});

	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		resetApiClient();
		act(() => {
			useAuthStore.getState().reset();
		});
	});

	it("認証済みユーザーが/settingsへアクセスするとAppLayout内に設定画面を表示する", async () => {
		const client = {
			get: vi.fn().mockResolvedValue({
				data: {
					id: "user-1", username: "taro", email: "taro@example.com",
					last_name: "山田", first_name: "太郎", last_name_kana: "ヤマダ", first_name_kana: "タロウ",
					birth_date: "1990-01-01", profile_completed: true, role: "member", has_password: true, oauth_providers: [],
				},
			}),
			interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
		} as unknown as AxiosInstance;
		vi.spyOn(axios, "create").mockReturnValue(client);
		act(() => {
			useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" } });
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.SETTINGS] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "アカウント設定" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "設定" })).toHaveAttribute("href", ROUTES.SETTINGS);
	});

	it("未認証で/へアクセスすると/loginへリダイレクトしログイン画面が描画される", async () => {
		act(() => {
			useAuthStore.setState({ status: "unauthenticated", user: null });
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.ROOT] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
	});

	it("認証済みで/へアクセスすると最終的に/dashboardへ到達する", async () => {
		act(() => {
			useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" } });
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.ROOT] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument();
	});

	it("認証済みユーザーが/loginへアクセスすると/dashboardへリダイレクトする", async () => {
		act(() => {
			useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" } });
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.LOGIN] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument();
	});

	it("未認証ユーザーが/registerへアクセスすると会員登録画面が描画される", async () => {
		act(() => {
			useAuthStore.setState({ status: "unauthenticated", user: null });
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.REGISTER] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "Cerberus 会員登録" })).toBeInTheDocument();
	});

	it("認証済みユーザーが/registerへアクセスすると/dashboardへリダイレクトする", async () => {
		act(() => {
			useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" } });
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.REGISTER] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument();
	});

	it.each([
		["unauthenticated" as const, ROUTES.PASSWORD_FORGOT, "パスワードをお忘れの方"],
		["authenticated" as const, ROUTES.PASSWORD_FORGOT, "パスワードをお忘れの方"],
		["unauthenticated" as const, ROUTES.PASSWORD_RESET, "新しいパスワードを設定"],
		["authenticated" as const, ROUTES.PASSWORD_RESET, "新しいパスワードを設定"],
		["unauthenticated" as const, ROUTES.VERIFY_EMAIL, "メールアドレスを確認中です"],
		["authenticated" as const, ROUTES.VERIFY_EMAIL, "メールアドレスを確認中です"],
	])("認証状態が%sでも%sへリダイレクトされずAuthLayout内に表示する", async (status, path, heading) => {
		act(() => {
			useAuthStore.setState(
				status === "authenticated"
					? { status, user: { id: "user-1", role: "member" } }
					: { status },
			);
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
		const pageHeading = screen.getByRole("heading", { name: heading });
		expect(pageHeading.closest(`.${styles.card}`)).not.toBeNull();
	});

	// issue #431: ログアウト後、実際のRequireAuth/RequireGuestガードとLoginPageを通じて
	// unauthenticated状態へ戻ることを結合テストで検証する（session/jwtいずれもauthStore.statusのみで判定される）。
	it("認証済みユーザーがログアウトすると実際の/loginへ遷移しCerberusログイン画面が表示される", async () => {
		const logout = vi.fn().mockResolvedValue(undefined);
		const adapter: AuthAdapter = {
			mode: "session",
			attach: (config) => config,
			onLoginSuccess: () => undefined,
			onUnauthorized: async () => false,
			restoreSession: async () => true,
			onLogout: () => undefined,
			logout,
		};
		act(() => {
			useAuthStore.setState({
				status: "authenticated",
				user: { id: "user-1", role: "member" },
				authAdapter: adapter,
			});
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [ROUTES.DASHBOARD] });
		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

		await act(async () => {
			render(
				<QueryClientProvider client={queryClient}>
					<RouterProvider router={router} />
				</QueryClientProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "ダッシュボード" })).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "ログアウト" }));

		expect(await screen.findByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
		expect(logout).toHaveBeenCalledOnce();
		expect(useAuthStore.getState().status).toBe("unauthenticated");
	});
});
