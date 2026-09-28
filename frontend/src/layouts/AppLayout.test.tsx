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
import { useProjectStore } from "../stores/projectStore";
import { AppLayout } from "./AppLayout";

/**
 * テスト用の認証adapterを生成し、指定された差分だけを上書きする。
 * @param overrides 既定adapterへ適用する部分的な上書き値。
 * @returns テスト用AuthAdapter。
 * @副作用 mock関数を生成するが、外部状態は変更しない。
 * @throws なし。
 */
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

/**
 * QueryClientとメモリールーターを含むAppLayoutのテスト環境を描画する。
 * @param props AppLayoutへ渡す任意のテストprops。
 * @returns 描画に利用したQueryClient。
 * @副作用 documentへReactツリーを描画する。
 * @throws React Testing Libraryの描画失敗時に例外を送出する。
 */
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
	render(
		<QueryClientProvider client={queryClient}>
			<RouterProvider router={router} />
		</QueryClientProvider>,
	);
	return queryClient;
}

/**
 * 未読件数APIと認証設定APIを返すfetchモックを登録する。
 * @param unreadCount モックレスポンスに含める未読件数。
 * @returns なし。
 * @副作用 global fetchをテスト用mockへ置き換える。
 * @throws なし。
 */
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
		act(() => useProjectStore.getState().clearSelectedProject());
	});

	/**
	 * admin認証済みの場合に共通リンク、通知ベル、管理リンクを表示することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 認証storeとDOMを一時的に変更する。
	 * @throws 表示内容が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
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

	/**
	 * member認証済みの場合に管理リンクを描画しないことを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 認証storeとDOMを一時的に変更する。
	 * @throws 管理リンクが表示された場合にVitestのアサーション例外を送出する。
	 */
	it("memberにはadminリンクを表示しない", () => {
		act(() => useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" }, authAdapter: createAuthAdapter() }));
		renderAppLayout();

		expect(screen.queryByRole("link", { name: "管理" })).not.toBeInTheDocument();
	});

	/**
	 * 通知項目クリックと全件既読操作を注入callbackへ接続することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 認証store、fetch mock、DOM、callback mockを一時的に変更する。
	 * @throws callbackが期待どおり呼ばれない場合にVitestのアサーション例外を送出する。
	 */
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

	/**
	 * ログアウト連打を抑止し、完了後に認証・選択状態を破棄してログインへ置換遷移することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 認証store、project store、DOM、QueryClientを一時的に変更する。
	 * @throws 遷移または状態破棄が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("ログアウトは二重実行せず、完了後にreplaceでログインへ遷移する", async () => {
		let resolveLogout: (() => void) | undefined;
		const logout = vi.fn(() => new Promise<void>((resolve) => (resolveLogout = resolve)));
		const adapter = createAuthAdapter({ logout });
		act(() => {
			useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" }, authAdapter: adapter });
			useProjectStore.getState().selectProject("project-1");
		});
		const queryClient = renderAppLayout();
		queryClient.setQueryData(["projects", { page: 1 }], { items: [{ id: "project-1" }] });

		const button = screen.getByRole("button", { name: "ログアウト" });
		fireEvent.click(button);
		fireEvent.click(button);
		expect(logout).toHaveBeenCalledOnce();
		expect(button).toBeDisabled();

		act(() => resolveLogout?.());
		expect(await screen.findByRole("heading", { name: "ログイン" })).toBeInTheDocument();
		expect(useAuthStore.getState().status).toBe("unauthenticated");
		expect(useProjectStore.getState().selectedProjectId).toBeNull();
		expect(queryClient.getQueryData(["projects", { page: 1 }])).toBeUndefined();
	});

	/**
	 * ハンバーガー操作で共通ナビの表示状態とARIA属性を切り替え、localStorageへ保存しないことを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 DOMとlocalStorageを一時的に変更する。
	 * @throws 開閉状態、ARIA属性、永続化状態が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("ハンバーガーでナビを開閉し、開閉状態を永続化しない", () => {
		localStorage.clear();
		renderAppLayout();

		const navigation = screen.getByRole("navigation", { name: "サイドバー" });
		const openButton = screen.getByRole("button", { name: "ナビゲーションを開く" });
		expect(openButton).toHaveAttribute("aria-expanded", "false");
		expect(navigation.className).not.toContain("navOpen");

		fireEvent.click(openButton);
		const closeButton = screen.getByRole("button", { name: "ナビゲーションを閉じる" });
		expect(closeButton).toHaveAttribute("aria-expanded", "true");
		expect(closeButton).toHaveAttribute("aria-controls", "app-navigation");
		expect(navigation).toHaveAttribute("id", "app-navigation");
		expect(navigation.className).toContain("navOpen");
		expect(localStorage.getItem("cerberus.ui")).toBeNull();

		fireEvent.click(closeButton);
		expect(screen.getByRole("button", { name: "ナビゲーションを開く" })).toHaveAttribute("aria-expanded", "false");
		expect(navigation.className).not.toContain("navOpen");
	});
});
