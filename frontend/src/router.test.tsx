import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { useAuthStore } from "./auth/authStore";
import { appRoutes } from "./router";
import { ROUTES } from "./routes";

describe("アプリケーションルート", () => {
	afterEach(() => {
		act(() => {
			useAuthStore.getState().reset();
		});
	});

	it("認証済みユーザーが/settingsへアクセスするとAppLayout内に設定画面を表示する", async () => {
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
});
