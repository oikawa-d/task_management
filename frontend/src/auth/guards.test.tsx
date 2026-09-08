import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { useAuthStore } from "./authStore";
import { RequireAdmin, RequireAuth, RequireGuest } from "./guards";
import { ROUTES } from "../routes";

function renderAdminUsersRoute() {
	const router = createMemoryRouter(
		[
			{ path: ROUTES.LOGIN, element: <h1>ログイン画面</h1> },
			{ path: ROUTES.DASHBOARD, element: <h1>ダッシュボード画面</h1> },
			{
				element: <RequireAdmin />,
				children: [{ path: ROUTES.ADMIN_USERS, element: <h1>ユーザー管理画面</h1> }],
			},
		],
		{ initialEntries: [ROUTES.ADMIN_USERS] },
	);

	return render(<RouterProvider router={router} />);
}

function renderDashboardRoute() {
	const router = createMemoryRouter(
		[
			{ path: ROUTES.LOGIN, element: <h1>ログイン画面</h1> },
			{
				element: <RequireAuth />,
				children: [{ path: ROUTES.DASHBOARD, element: <h1>ダッシュボード画面</h1> }],
			},
		],
		{ initialEntries: [ROUTES.DASHBOARD] },
	);

	return render(<RouterProvider router={router} />);
}

function renderLoginRoute() {
	const router = createMemoryRouter(
		[
			{ path: ROUTES.DASHBOARD, element: <h1>ダッシュボード画面</h1> },
			{
				element: <RequireGuest />,
				children: [{ path: ROUTES.LOGIN, element: <h1>ログイン画面</h1> }],
			},
		],
		{ initialEntries: [ROUTES.LOGIN] },
	);

	return render(<RouterProvider router={router} />);
}

describe("RequireAuth", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("redirects unauthenticated access from /dashboard to /login", async () => {
		useAuthStore.setState({ status: "unauthenticated", user: null });

		renderDashboardRoute();

		expect(await screen.findByRole("heading", { name: "ログイン画面" })).toBeInTheDocument();
	});

	it("renders the dashboard route content for an authenticated user", async () => {
		useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" } });

		renderDashboardRoute();

		expect(await screen.findByRole("heading", { name: "ダッシュボード画面" })).toBeInTheDocument();
	});
});

describe("RequireGuest", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("redirects authenticated access from /login to /dashboard", async () => {
		useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" } });

		renderLoginRoute();

		expect(await screen.findByRole("heading", { name: "ダッシュボード画面" })).toBeInTheDocument();
	});

	it("renders the login route content for an unauthenticated user", async () => {
		useAuthStore.setState({ status: "unauthenticated", user: null });

		renderLoginRoute();

		expect(await screen.findByRole("heading", { name: "ログイン画面" })).toBeInTheDocument();
	});
});

describe("RequireAdmin", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("redirects unauthenticated access from /admin/users to /login", async () => {
		useAuthStore.setState({ status: "unauthenticated", user: null });

		renderAdminUsersRoute();

		expect(await screen.findByRole("heading", { name: "ログイン画面" })).toBeInTheDocument();
	});

	it("redirects member role access from /admin/users to /dashboard", async () => {
		useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "member" } });

		renderAdminUsersRoute();

		expect(await screen.findByRole("heading", { name: "ダッシュボード画面" })).toBeInTheDocument();
	});

	it("renders the admin route content for admin role", async () => {
		useAuthStore.setState({ status: "authenticated", user: { id: "u2", role: "admin" } });

		renderAdminUsersRoute();

		expect(await screen.findByRole("heading", { name: "ユーザー管理画面" })).toBeInTheDocument();
	});
});
