import { describe, expect, it } from "vitest";

import { BREAKPOINTS } from "./breakpoints";

const components = import.meta.glob("../**/*.tsx", { eager: true, query: "?raw", import: "default" }) as Record<string, string | { default: string }>;
const styles = import.meta.glob("../**/*.css", { eager: true, query: "?raw", import: "default" }) as Record<string, string | { default: string }>;

/**
 * Viteのraw import結果を本文の文字列へ正規化する。
 * @param value 文字列またはdefaultプロパティを持つrawモジュール。
 * @returns 検証対象のファイル本文。
 * @副作用 なし。
 * @throws 例外を送出しない。
 */
function sourceOf(value: string | { default: string }): string {
	return typeof value === "string" ? value : value.default;
}

const rawStyles = Object.fromEntries(Object.entries(styles).map(([path, source]) => [path, sourceOf(source)]));

describe("UIスタイリング契約", () => {
	/** Viteのraw importが文字列形式とdefault形式のどちらでも本文化できることを検証する。 */
	it("raw CSS importの両形式を正規化する", () => {
		expect(sourceOf(".sample {}")).toBe(".sample {}");
		expect(sourceOf({ default: ".sample {}" })).toBe(".sample {}");
	});

	/** DOMを描画するコンポーネントへ意味のあるclassNameが適用されていることを検証する。 */
	it("DOMを描画する非テストコンポーネントはclassNameを持つ", () => {
		const nonVisual = new Set(["../App.tsx", "../main.tsx", "../router.tsx", "../auth/AuthProvider.tsx"]);
		const unstyled = Object.entries(components).filter(([path, source]) => {
			if (path.endsWith(".test.tsx") || nonVisual.has(path)) return false;
			const text = sourceOf(source);
			return /export function [A-Z]\w+/.test(text) && !text.includes("className=");
		}).map(([path]) => path);
		expect(unstyled).toEqual([]);
	});

	/** responsive境界値がbreakpoints.tsとtokens.cssで一致することを検証する。 */
	it("レスポンシブ境界値を共通定数で管理する", () => {
		expect(BREAKPOINTS).toEqual({ sm: "30rem", md: "48rem", lg: "90rem" });
		const tokenText = rawStyles["./tokens.css"] ?? "";
		for (const [name, value] of Object.entries(BREAKPOINTS)) expect(tokenText).toContain(`--breakpoint-${name}: ${value};`);
	});

	/** CSS media queryの幅が共通breakpoint定義だけで構成されることを検証する。 */
	it("全media queryの幅がbreakpoints.tsとtokens.cssの値に一致する", () => {
		const allowed = new Set<string>(Object.values(BREAKPOINTS));
		const mediaValues = Object.entries(rawStyles).flatMap(([path, source]) => {
			if (path.endsWith("/tokens.css")) return [];
			return [...sourceOf(source).matchAll(/@media[^{}]*(?:min|max)-width\s*:\s*([^\s)]+)/g)].map((match) => ({ path, value: match[1] }));
		});
		expect(mediaValues.every((value) => allowed.has(value.value)), mediaValues.map((value) => `${value.path}: ${value.value}`).join("\n")).toBe(true);
	});

	/** CSSの寸法・アニメーション時間がトークン化されていることを検証する。 */
	it("CSSの寸法値はトークンへ集約されている", () => {
		const violations = Object.entries(rawStyles).flatMap(([path, source]) => {
			if (path.endsWith("/tokens.css")) return [];
			const declarations = sourceOf(source).replace(/(?:min|max)-width\s*:\s*[^\s)]+/g, "width: var(--breakpoint)");
			return declarations.split("\n").flatMap((line, index) => [...line.matchAll(/\b\d+(?:\.\d+)?(?:px|rem|s|ms)\b/g)].map((match) => `${path}:${index + 1}:${match[0]}`));
		});
		expect(violations).toEqual([]);
	});

	/** 狭い画面でもboardと管理テーブルが横方向へ収まることを検証する。 */
	it("狭い画面ではboardとテーブルが横スクロールを担保する", () => {
		const raw = rawStyles;
		const board = raw["../features/board/BoardPage.module.css"];
		const table = raw["../features/admin/components/AdminTable.module.css"];
		expect(board).toContain("overflow-x: auto");
		expect(table).toContain("overflow-x: auto");
	});

	/** 管理系三画面が共通のテーブルCSS moduleを参照することを検証する。 */
	it("管理・プロジェクト・ログイン履歴の3テーブルは共通CSS moduleを使う", () => {
		for (const path of ["../features/admin/components/UserTable.tsx", "../features/admin/components/ProjectTable.tsx", "../features/settings/components/LoginHistoryTable.tsx"]) {
			expect(sourceOf(components[path]), path).toContain('AdminTable.module.css');
		}
	});
});
