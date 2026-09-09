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

	it.each([
		["unauthenticated" as const, ROUTES.PASSWORD_FORGOT, "パスワードをお忘れの方"],
		["authenticated" as const, ROUTES.PASSWORD_FORGOT, "パスワードをお忘れの方"],
		["unauthenticated" as const, ROUTES.PASSWORD_RESET, "新しいパスワードを設定"],
		["authenticated" as const, ROUTES.PASSWORD_RESET, "新しいパスワードを設定"],
		["unauthenticated" as const, ROUTES.VERIFY_EMAIL, "メールアドレスを確認中です"],
		["authenticated" as const, ROUTES.VERIFY_EMAIL, "メールアドレスを確認中です"],
	])("認証状態が%sでも%sへリダイレクトされず画面を表示する", async (status, path, heading) => {
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
	});
});
