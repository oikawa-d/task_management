import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
	it("renders the login page by default via the router", async () => {
		render(<App />);

		expect(await screen.findByRole("heading", { name: "ログイン" })).toBeInTheDocument();
	});
});
