import { describe, expect, it } from "vitest";

type RawStyleModule = string | { default: string };

const featureStyles = import.meta.glob("../features/**/*.css", {
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
	it("features配下に生の16進色を残さない", () => {
		const rawHexValues = Object.entries(featureStyles).flatMap(([path, style]) =>
			toCssText(style)
				.split("\n")
				.filter((line) => /#[0-9a-fA-F]{3,8}\b/.test(line) && !line.includes("var(--"))
				.map((line) => `${path}: ${line.trim()}`),
		);

		expect(rawHexValues).toEqual([]);
	});

	it("参照する色トークンを定義する", () => {
		const references = new Set(
			Object.values(featureStyles).flatMap((style) =>
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
});
