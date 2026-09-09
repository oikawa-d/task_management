import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { DashboardPage } from "./DashboardPage";

function LocationDisplay() {
	const location = useLocation();
	return <output data-testid="location">{location.pathname}</output>;
}

describe("DashboardPage", () => {
	it("一覧、作成導線、calendar領域を表示する", () => {
		render(<MemoryRouter><DashboardPage /></MemoryRouter>);

		expect(screen.getByRole("heading", { name: "プロジェクト一覧" })).toBeInTheDocument();
		expect(screen.getByRole("heading", { name: "期限カレンダー" })).toBeInTheDocument();
		expect(screen.getByText("プロジェクトがありません。")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "Cerberus" } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));

		expect(screen.getByRole("button", { name: "Cerberus" })).toBeInTheDocument();
	});

	it("プロジェクト選択時にboardへ遷移する", () => {
		render(<MemoryRouter><DashboardPage /><LocationDisplay /></MemoryRouter>);
		fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
		fireEvent.change(screen.getByLabelText("プロジェクト名"), { target: { value: "Cerberus" } });
		fireEvent.click(screen.getByRole("button", { name: "作成" }));
		fireEvent.click(screen.getByRole("button", { name: "Cerberus" }));

		expect(screen.getByTestId("location").textContent).toMatch(/^\/projects\//);
	});
});
