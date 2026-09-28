import { describe, expect, it } from "vitest";
type RawStyleModule = string | { default: string };

const allStyles = import.meta.glob("../**/*.css", {
	eager: true,
	query: "?raw",
	import: "default",
}) as Record<string, RawStyleModule>;
const tokenStyles = import.meta.glob("./tokens.css", {
	eager: true,
	query: "?raw",
	import: "default",
}) as Record<string, RawStyleModule>;

/**
 * Viteのraw CSS import結果を本文の文字列へ正規化する。
 * @param value 文字列またはdefaultプロパティを持つraw CSSモジュール。
 * @returns 検証対象のCSS本文。
 * @副作用 なし。
 * @throws 例外を送出しない。
 */
const toRawCssText = (value: RawStyleModule): string => typeof value === "string" ? value : value.default;

/**
 * CSSブロックから色トークン名と値を抽出する。
 * @param block 色トークン宣言を含むCSSブロック。
 * @returns 色トークン名をキー、正規化した値を値とするオブジェクト。
 * @副作用 なし。
 * @throws 例外を送出しない。
 */
const extractColorTokens = (block: string): Record<string, string> => Object.fromEntries(
	[...block.matchAll(/(--color-[\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]),
);

const styleEntries = Object.entries(allStyles);
const tokenText = Object.values(tokenStyles).map(toRawCssText)[0] ?? "";

describe("CSS color tokens", () => {
	/** Viteのraw importが文字列形式とdefault形式のどちらでも本文化できることを検証する。 */
	it("raw CSS importの両形式を正規化する", () => {
		expect(toRawCssText(".sample {}")).toBe(".sample {}");
		expect(toRawCssText({ default: ".sample {}" })).toBe(".sample {}");
	});

	/** コンポーネントCSSに色のハードコードがないことを検証する。 */
	it("コンポーネントCSSに色のハードコードを残さない", () => {
		const rawColors = styleEntries.filter(([path]) => !path.endsWith("tokens.css")).flatMap(([path, source]) =>
			toRawCssText(source)
				.split("\n")
				.filter((line) => /#[0-9a-fA-F]{3,8}\b|\brgb\(|\brgba\(|(?:color|background(?:-color)?|border(?:-[\w-]+)?|outline(?:-[\w-]+)?)[^:]*:\s*[^;]*(?:\bwhite\b|\bblack\b)/i.test(line))
				.map((line) => `${path}: ${line.trim()}`),
		);

		expect(rawColors).toEqual([]);
	});

	/** 参照された色トークンが定義済みであることを検証する。 */
	it("参照する色トークンを定義する", () => {
		const references = new Set(
			styleEntries.flatMap(([, source]) =>
				[...toRawCssText(source).matchAll(/var\(\s*(--color-[\w-]+)/g)].map((match) => match[1]),
			),
		);
		const definitions = new Set(
			Object.keys(extractColorTokens(tokenText)),
		);

		for (const reference of references) {
			expect(definitions).toContain(reference);
		}
	});

	/** lightテーマの全色トークンにexplicit darkテーマ値があることを検証する。 */
	it("全カラートークンにダークテーマ値を定義する", () => {
		const lightBlock = tokenText.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const darkBlock = tokenText.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const darkTokens = extractColorTokens(darkBlock);
		for (const token of Object.keys(extractColorTokens(lightBlock))) expect(darkTokens).toHaveProperty(token);
	});

	/** explicit darkとOS追従system darkの色トークン名・値が一致することを検証する。 */
	it("明示的ダークテーマとOS追従ダークテーマの色トークン値が一致する", () => {
		const explicitDarkBlock = tokenText.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const systemDarkBlock = tokenText.match(/@media\s*\(prefers-color-scheme:\s*dark\)[\s\S]*?:root:not\(\[data-theme\]\)\s*\{([\s\S]*?)\n\s*\}\s*\}/)?.[1] ?? "";
		expect(extractColorTokens(systemDarkBlock)).toEqual(extractColorTokens(explicitDarkBlock));
	});
});
