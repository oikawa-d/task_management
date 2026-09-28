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
const EXPECTED_COLOR_TOKENS = [
	"--color-page", "--color-overlay", "--color-text-primary", "--color-text-secondary", "--color-text-tertiary", "--color-muted",
	"--color-surface", "--color-surface-muted", "--color-border", "--color-border-light", "--color-border-subtle", "--color-border-muted",
	"--color-border-placeholder", "--color-accent", "--color-accent-strong", "--color-accent-surface", "--color-danger", "--color-danger-fg",
	"--color-danger-surface", "--color-success", "--color-success-surface", "--color-warning", "--color-warning-surface", "--color-warning-border",
	"--color-focus", "--color-header-bg", "--color-header-fg", "--color-header-hover", "--color-header-badge-fg", "--color-row-hover",
];

describe("CSS color tokens", () => {
	/**
	 * Viteのraw importが文字列形式とdefault形式のどちらでも本文へ正規化できることを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 テスト用値のみを評価し、外部状態を変更しない。
	 * @throws 期待値不一致時にVitestのアサーション例外を送出する。
	 */
	it("raw CSS importの両形式を正規化する", () => {
		expect(toRawCssText(".sample {}")).toBe(".sample {}");
		expect(toRawCssText({ default: ".sample {}" })).toBe(".sample {}");
		expect(styleEntries.length).toBeGreaterThan(0);
		expect(styleEntries.every(([path]) => path.length > 0)).toBe(true);
		expect(tokenText.trim().length).toBeGreaterThan(0);
	});

	/**
	 * コンポーネントCSSに色のハードコードがないことを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 raw CSS本文を読み取るが、ファイルは変更しない。
	 * @throws ハードコード色を検出した場合にVitestのアサーション例外を送出する。
	 */
	it("コンポーネントCSSに色のハードコードを残さない", () => {
		const rawColors = styleEntries.filter(([path]) => !path.endsWith("tokens.css")).flatMap(([path, source]) =>
			toRawCssText(source)
				.split("\n")
				.filter((line) => /#[0-9a-fA-F]{3,8}\b|\brgb\(|\brgba\(|(?:color|background(?:-color)?|border(?:-[\w-]+)?|outline(?:-[\w-]+)?)[^:]*:\s*[^;]*(?:\bwhite\b|\bblack\b)/i.test(line))
				.map((line) => `${path}: ${line.trim()}`),
		);

		expect(rawColors).toEqual([]);
	});

	/**
	 * 参照された色トークンが定義済みであることを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 raw CSS本文を読み取るが、ファイルは変更しない。
	 * @throws 未定義トークンを検出した場合にVitestのアサーション例外を送出する。
	 */
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

	/**
	 * lightテーマの全色トークンにexplicit darkテーマ値があることを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 raw CSS本文を読み取るが、ファイルは変更しない。
	 * @throws dark値が欠落した場合にVitestのアサーション例外を送出する。
	 */
	it("全カラートークンにダークテーマ値を定義する", () => {
		const lightBlock = tokenText.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const darkBlock = tokenText.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const lightTokens = extractColorTokens(lightBlock);
		const darkTokens = extractColorTokens(darkBlock);
		expect(Object.keys(lightTokens).length).toBeGreaterThan(0);
		expect(Object.keys(darkTokens).length).toBeGreaterThan(0);
		expect(Object.keys(lightTokens).sort()).toEqual([...EXPECTED_COLOR_TOKENS].sort());
		expect(Object.keys(darkTokens).sort()).toEqual([...EXPECTED_COLOR_TOKENS].sort());
		for (const token of Object.keys(lightTokens)) expect(darkTokens).toHaveProperty(token);
	});

	/**
	 * explicit darkとOS追従system darkの色トークン名・値が一致することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 raw CSS本文を読み取るが、ファイルは変更しない。
	 * @throws テーマ間の集合または値が異なる場合にVitestのアサーション例外を送出する。
	 */
	it("明示的ダークテーマとOS追従ダークテーマの色トークン値が一致する", () => {
		const explicitDarkBlock = tokenText.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const systemDarkBlock = tokenText.match(/@media\s*\(prefers-color-scheme:\s*dark\)[\s\S]*?:root:not\(\[data-theme\]\)\s*\{([\s\S]*?)\n\s*\}\s*\}/)?.[1] ?? "";
		const explicitTokens = extractColorTokens(explicitDarkBlock);
		const systemTokens = extractColorTokens(systemDarkBlock);
		expect(Object.keys(explicitTokens).length).toBeGreaterThan(0);
		expect(Object.keys(systemTokens).length).toBeGreaterThan(0);
		expect(Object.keys(explicitTokens).sort()).toEqual([...EXPECTED_COLOR_TOKENS].sort());
		expect(Object.keys(systemTokens).sort()).toEqual([...EXPECTED_COLOR_TOKENS].sort());
		expect(systemTokens).toEqual(explicitTokens);
	});
});
