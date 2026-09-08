import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { useAuthStore } from "./authStore";
import { RequireAdmin } from "./guards";
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
