import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { AppLayout } from "./AppLayout";
import { useAuthStore } from "../auth/authStore";
import { ROUTES } from "../routes";

function renderAppLayout() {
	const router = createMemoryRouter(
		[
			{
				element: <AppLayout />,
				children: [{ path: ROUTES.DASHBOARD, element: <p>ダッシュボード</p> }],
			},
		],
		{ initialEntries: [ROUTES.DASHBOARD] },
	);

	return render(<RouterProvider router={router} />);
}

describe("AppLayout", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("shows the admin link for admin role", () => {
		useAuthStore.setState({ status: "authenticated", user: { id: "u1", role: "admin" } });

		renderAppLayout();

		expect(screen.getByRole("link", { name: "管理" })).toBeInTheDocument();
	});

	it("hides the admin link for member role", () => {
		useAuthStore.setState({ status: "authenticated", user: { id: "u2", role: "member" } });

		renderAppLayout();

		expect(screen.queryByRole("link", { name: "管理" })).not.toBeInTheDocument();
	});
});
