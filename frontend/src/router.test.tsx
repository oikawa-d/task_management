import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { createAppRouter } from "./router";

describe("application routes", () => {
	it("renders BoardPage for a project route", () => {
		render(<RouterProvider router={createAppRouter(["/projects/project-1"])} />);

		expect(screen.getByRole("heading", { name: "プロジェクト project-1" })).toBeInTheDocument();
	});

	it("supports the task detail URL under the project route", () => {
		render(<RouterProvider router={createAppRouter(["/projects/project-1/tasks/task-1"])} />);

		expect(screen.getByRole("heading", { name: "プロジェクト project-1" })).toBeInTheDocument();
	});
});
