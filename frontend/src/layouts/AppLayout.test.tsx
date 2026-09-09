import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter } from "../api/authAdapter/client";
import type { AuthAdapter } from "../api/authAdapter";
import { useAuthStore } from "../auth/authStore";
import { buildNotification } from "../features/notifications/testFixtures";
import { ROUTES } from "../routes";
import { AppLayout } from "./AppLayout";

function createAuthAdapter(overrides: Partial<AuthAdapter> = {}): AuthAdapter {
	return {
		mode: "session",
		attach: (config) => config,
		onLoginSuccess: vi.fn(),
		onUnauthorized: vi.fn(async () => false),
		restoreSession: vi.fn(async () => true),
		onLogout: vi.fn(),
		logout: vi.fn(async () => undefined),
		...overrides,
	};
}

function renderAppLayout(props: Parameters<typeof AppLayout>[0] = {}) {
	const router = createMemoryRouter(
		[
			{
				element: <AppLayout {...props} />,
				children: [{ path: ROUTES.DASHBOARD, element: <p>ダッシュボード</p> }],
			},
			{ path: ROUTES.LOGIN, element: <h1>ログイン</h1> },
		],
		{ initialEntries: [ROUTES.DASHBOARD] },
	);
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return render(
		<QueryClientProvider client={queryClient}>
			<RouterProvider router={router} />
		</QueryClientProvider>,
	);
}

function mockUnreadCount(unreadCount: number) {
	vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
		const body = String(input).endsWith("/auth/config") ? { auth_mode: "session" } : { unread_count: unreadCount };
		return Promise.resolve({ ok: true, status: 200, json: async () => body });
	}));
}

describe("AppLayout", () => {
	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
		clearAuthAdapter();
		act(() => useAuthStore.getState().reset());
	});

	it("設定リンク・通知ベル・adminリンクを実アプリ用レイアウトで表示する", async () => {
		mockUnreadCount(3);
		act(() => {
			useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "admin" }, authAdapter: createAuthAdapter() });
		});

		renderAppLayout({ notifications: [buildNotification()], notificationTotalPages: 2 });

		expect(await screen.findByText("ダッシュボード")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "設定" })).toHaveAttribute("href", ROUTES.SETTINGS);
		expect(screen.getByRole("link", { name: "管理" })).toHaveAttribute("href", ROUTES.ADMIN_USERS);
		expect(screen.getByRole("button", { name: "通知" })).toBeInTheDocument();
		expect(await screen.findByLabelText("未読 3 件")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		expect(await screen.findByText("設計書をレビューする")).toBeInTheDocument();
	});

	it("memberにはadminリンクを表示しない", () => {
		act(() => useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" }, authAdapter: createAuthAdapter() }));
		renderAppLayout();

		expect(screen.queryByRole("link", { name: "管理" })).not.toBeInTheDocument();
	});

	it("通知操作callbackを注入値へ接続する", async () => {
		const onItemClick = vi.fn();
		const onMarkAllRead = vi.fn();
		mockUnreadCount(1);
		act(() => useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" }, authAdapter: createAuthAdapter() }));
		renderAppLayout({ notifications: [buildNotification()], onNotificationItemClick: onItemClick, onMarkAllNotificationsRead: onMarkAllRead });

		expect(await screen.findByLabelText("未読 1 件")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		fireEvent.click(await screen.findByText("設計書をレビューする"));
		expect(onItemClick).toHaveBeenCalledOnce();
		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		fireEvent.click(screen.getByRole("button", { name: "すべて既読" }));
		expect(onMarkAllRead).toHaveBeenCalledOnce();
	});

	it("ログアウトは二重実行せず、完了後にreplaceでログインへ遷移する", async () => {
		let resolveLogout: (() => void) | undefined;
		const logout = vi.fn(() => new Promise<void>((resolve) => (resolveLogout = resolve)));
		const adapter = createAuthAdapter({ logout });
		act(() => useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" }, authAdapter: adapter }));
		renderAppLayout();

		const button = screen.getByRole("button", { name: "ログアウト" });
		fireEvent.click(button);
		fireEvent.click(button);
		expect(logout).toHaveBeenCalledOnce();
		expect(button).toBeDisabled();

		act(() => resolveLogout?.());
		expect(await screen.findByRole("heading", { name: "ログイン" })).toBeInTheDocument();
		expect(useAuthStore.getState().status).toBe("unauthenticated");
	});
});
