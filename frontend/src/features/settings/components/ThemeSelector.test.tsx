import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useUiStore } from "../../../stores/uiStore";
import { ThemeSelector } from "./ThemeSelector";

describe("ThemeSelector", () => {
	afterEach(() => {
		useUiStore.setState({ theme: "system", fontScale: 1 });
		document.documentElement.removeAttribute("data-theme");
	});

	it("テーマを選択できる", () => {
		render(<ThemeSelector />);
		fireEvent.change(screen.getByRole("combobox", { name: "テーマ" }), { target: { value: "dark" } });
		expect(useUiStore.getState().theme).toBe("dark");
		expect(document.documentElement.dataset.theme).toBe("dark");
	});
});
