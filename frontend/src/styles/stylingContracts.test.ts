import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { BREAKPOINTS } from "./breakpoints";

const components = import.meta.glob("../**/*.tsx", { eager: true, query: "?raw", import: "default" }) as Record<string, string | { default: string }>;
const styles = import.meta.glob("../**/*.css", { eager: true, query: "?raw", import: "default" }) as Record<string, string | { default: string }>;

function sourceOf(value: string | { default: string }): string {
	return typeof value === "string" ? value : value.default;
}

function rawStyles(): Record<string, string> {
	return Object.fromEntries(Object.keys(styles).map((path) => [path, readFileSync(resolve(process.cwd(), "src/styles", path), "utf8")]));
}

describe("UIスタイリング契約", () => {
	it("DOMを描画する非テストコンポーネントはclassNameを持つ", () => {
		const nonVisual = new Set(["../App.tsx", "../main.tsx", "../router.tsx", "../auth/AuthProvider.tsx"]);
		const unstyled = Object.entries(components).filter(([path, source]) => {
			if (path.endsWith(".test.tsx") || nonVisual.has(path)) return false;
			const text = sourceOf(source);
			return /export function [A-Z]\w+/.test(text) && !text.includes("className=");
		}).map(([path]) => path);
		expect(unstyled).toEqual([]);
	});

	it("レスポンシブ境界値を共通定数で管理する", () => {
		expect(BREAKPOINTS).toEqual({ sm: "30rem", md: "48rem", lg: "90rem" });
		const tokenText = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");
		for (const [name, value] of Object.entries(BREAKPOINTS)) expect(tokenText).toContain(`--breakpoint-${name}: ${value};`);
	});

	it("全media queryの幅がbreakpoints.tsとtokens.cssの値に一致する", () => {
		const allowed = new Set<string>(Object.values(BREAKPOINTS));
		const mediaValues = Object.entries(rawStyles()).flatMap(([path, source]) => {
			if (path.endsWith("/tokens.css")) return [];
			return [...sourceOf(source).matchAll(/@media[^{}]*(?:min|max)-width\s*:\s*([^\s)]+)/g)].map((match) => ({ path, value: match[1] }));
		});
		expect(mediaValues.every((value) => allowed.has(value.value)), mediaValues.map((value) => `${value.path}: ${value.value}`).join("\n")).toBe(true);
	});

	it("CSSの寸法値はトークンへ集約されている", () => {
		const violations = Object.entries(rawStyles()).flatMap(([path, source]) => {
			if (path.endsWith("/tokens.css")) return [];
			const declarations = sourceOf(source).replace(/(?:min|max)-width\s*:\s*[^\s)]+/g, "width: var(--breakpoint)");
			return declarations.split("\n").flatMap((line, index) => [...line.matchAll(/\b\d+(?:\.\d+)?(?:px|rem|s|ms)\b/g)].map((match) => `${path}:${index + 1}:${match[0]}`));
		});
		expect(violations).toEqual([]);
	});

	it("狭い画面ではboardとテーブルが横スクロールを担保する", () => {
		const raw = rawStyles();
		const board = raw["../features/board/BoardPage.module.css"];
		const table = raw["../features/admin/components/AdminTable.module.css"];
		expect(board).toContain("overflow-x: auto");
		expect(table).toContain("overflow-x: auto");
	});

	it("管理・プロジェクト・ログイン履歴の3テーブルは共通CSS moduleを使う", () => {
		for (const path of ["../features/admin/components/UserTable.tsx", "../features/admin/components/ProjectTable.tsx", "../features/settings/components/LoginHistoryTable.tsx"]) {
			expect(sourceOf(components[path]), path).toContain('AdminTable.module.css');
		}
	});
});
