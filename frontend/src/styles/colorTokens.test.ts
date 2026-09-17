import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

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

const toRawCssText = (path: string): string => readFileSync(resolve(process.cwd(), "src/styles", path), "utf8");

describe("CSS color tokens", () => {
	it("コンポーネントCSSに色のハードコードを残さない", () => {
		const rawColors = Object.keys(allStyles).filter((path) => !path.endsWith("tokens.css")).flatMap((path) =>
			toRawCssText(path)
				.split("\n")
				.filter((line) => /#[0-9a-fA-F]{3,8}\b|\brgb\(|\brgba\(|(?:color|background(?:-color)?|border(?:-[\w-]+)?|outline(?:-[\w-]+)?)[^:]*:\s*[^;]*(?:\bwhite\b|\bblack\b)/i.test(line))
				.map((line) => `${path}: ${line.trim()}`),
		);

		expect(rawColors).toEqual([]);
	});

	it("参照する色トークンを定義する", () => {
		const references = new Set(
			Object.keys(allStyles).flatMap((path) =>
				[...toRawCssText(path).matchAll(/var\(\s*(--color-[\w-]+)/g)].map((match) => match[1]),
			),
		);
		const definitions = new Set(
			Object.keys(tokenStyles).flatMap((path) =>
				[...toRawCssText(path).matchAll(/(--color-[\w-]+)\s*:/g)].map((match) => match[1]),
			),
		);

		for (const reference of references) {
			expect(definitions).toContain(reference);
		}
	});

	it("全カラートークンにダークテーマ値を定義する", () => {
		const tokenText = toRawCssText(Object.keys(tokenStyles)[0]);
		const lightBlock = tokenText.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const darkBlock = tokenText.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
		const lightTokens = [...lightBlock.matchAll(/(--color-[\w-]+)\s*:/g)].map((match) => match[1]);
		for (const token of lightTokens) expect(darkBlock).toContain(`${token}:`);
	});
});
