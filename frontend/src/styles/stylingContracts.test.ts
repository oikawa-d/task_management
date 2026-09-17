import { describe, expect, it } from "vitest";

import { BREAKPOINTS } from "./breakpoints";

const components = import.meta.glob("../**/*.tsx", { eager: true, query: "?raw", import: "default" }) as Record<string, string | { default: string }>;

describe("UIスタイリング契約", () => {
	it("DOMを描画する非テストコンポーネントはclassNameを持つ", () => {
		const nonVisual = new Set(["../App.tsx", "../main.tsx", "../router.tsx", "../auth/AuthProvider.tsx"]);
		const unstyled = Object.entries(components).filter(([path, source]) => {
			if (path.endsWith(".test.tsx") || nonVisual.has(path)) return false;
			const text = typeof source === "string" ? source : source.default;
			return /export function [A-Z]\w+/.test(text) && !text.includes("className=");
		}).map(([path]) => path);
		expect(unstyled).toEqual([]);
	});

	it("レスポンシブ境界値を共通定数で管理する", () => {
		expect(BREAKPOINTS).toEqual({ sm: "30rem", md: "48rem", lg: "90rem" });
	});
});
