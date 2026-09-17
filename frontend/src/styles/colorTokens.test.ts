import { describe, expect, it } from "vitest";

type RawStyleModule = string | { default: string };

const allStyles = import.meta.glob("../**/*.css", {
	eager: true,
	import: "default",
	query: "?raw",
}) as Record<string, RawStyleModule>;
const tokenStyles = import.meta.glob("./tokens.css", {
	eager: true,
	import: "default",
	query: "?raw",
}) as Record<string, RawStyleModule>;

const toCssText = (style: RawStyleModule): string =>
	typeof style === "string" ? style : style.default;

describe("CSS color tokens", () => {
	it("コンポーネントCSSに色のハードコードを残さない", () => {
		const rawColors = Object.entries(allStyles).filter(([path]) => !path.endsWith("tokens.css")).flatMap(([path, style]) =>
			toCssText(style)
				.split("\n")
				.filter((line) => /#[0-9a-fA-F]{3,8}\b|\brgb\(|\brgba\(|\b(?:white|black)\b/i.test(line))
				.map((line) => `${path}: ${line.trim()}`),
		);

		expect(rawColors).toEqual([]);
	});

	it("参照する色トークンを定義する", () => {
		const references = new Set(
			Object.values(allStyles).flatMap((style) =>
				[...toCssText(style).matchAll(/var\(\s*(--color-[\w-]+)/g)].map((match) => match[1]),
			),
		);
		const definitions = new Set(
			Object.values(tokenStyles).flatMap((style) =>
				[...toCssText(style).matchAll(/(--color-[\w-]+)\s*:/g)].map((match) => match[1]),
			),
		);

		for (const reference of references) {
			expect(definitions).toContain(reference);
		}
	});

	it("全カラートークンにダークテーマ値を定義する", () => {
		const tokenText = toCssText(Object.values(tokenStyles)[0]);
		const lightBlock = tokenText.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const darkBlock = tokenText.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const lightTokens = [...lightBlock.matchAll(/(--color-[\w-]+)\s*:/g)].map((match) => match[1]);
		for (const token of lightTokens) expect(darkBlock).toContain(`${token}:`);
	});
});
