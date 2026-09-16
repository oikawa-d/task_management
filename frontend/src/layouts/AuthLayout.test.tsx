import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthLayout } from "./AuthLayout";

describe("AuthLayout", () => {
	it("子ルートの内容をOutlet経由で表示する", () => {
		const router = createMemoryRouter(
			[
				{
					element: <AuthLayout />,
					children: [{ path: "/login", element: <h1>Cerberus</h1> }],
				},
			],
			{ initialEntries: ["/login"] },
		);

		render(<RouterProvider router={router} />);

		expect(screen.getByRole("heading", { name: "Cerberus" })).toBeInTheDocument();
	});
});
