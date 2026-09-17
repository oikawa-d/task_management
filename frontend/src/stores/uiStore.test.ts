import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useUiStore } from "./uiStore";

describe("uiStore theme", () => {
	afterEach(() => {
		useUiStore.setState({ theme: "system", fontScale: 1 });
		document.documentElement.removeAttribute("data-theme");
		localStorage.clear();
	});

	it("light/darkをdata-themeへ即時反映する", () => {
		const { result } = renderHook(() => useUiStore());
		act(() => result.current.setTheme("dark"));
		expect(document.documentElement.dataset.theme).toBe("dark");
		act(() => result.current.setTheme("light"));
		expect(document.documentElement.dataset.theme).toBe("light");
	});

	it("systemではdata-themeを外し、状態を保持する", () => {
		document.documentElement.dataset.theme = "dark";
		const { result } = renderHook(() => useUiStore());
		act(() => result.current.setTheme("system"));
		expect(result.current.theme).toBe("system");
		expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
	});
});
