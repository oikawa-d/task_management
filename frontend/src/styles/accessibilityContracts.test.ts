import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const tokenCss = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

const css = tokenCss;

function block(selector: string): string {
	const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	return css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\n\\}`, "m"))?.[1] ?? "";
}

function colors(source: string): Record<string, string> {
	return Object.fromEntries([...source.matchAll(/(--color-[\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]));
}

function luminance(value: string): number {
	const parts = value.match(/rgb\(\s*(\d+)\s+(\d+)\s+(\d+)/);
	if (!parts) throw new Error(`Unsupported token color: ${value}`);
	const channels = parts.slice(1, 4).map((part) => Number(part) / 255).map((channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
	return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

describe("アクセシビリティ契約", () => {
	it("light/darkの主要な文字色と背景色がWCAG AAを満たす", () => {
		expect(css.length).toBeGreaterThan(100);
		const pairs = [["--color-text-primary", "--color-page"], ["--color-text-primary", "--color-surface"], ["--color-text-secondary", "--color-surface"], ["--color-accent-strong", "--color-page"], ["--color-danger-fg", "--color-danger-surface"], ["--color-success", "--color-success-surface"], ["--color-header-fg", "--color-header-bg"]];
		for (const selector of [":root", ':root[data-theme="dark"]']) {
			const palette = colors(block(selector));
			for (const [foreground, background] of pairs) {
				expect(palette[foreground], `${selector} missing ${foreground}`).toBeDefined();
				expect(palette[background], `${selector} missing ${background}`).toBeDefined();
				const ratio = (Math.max(luminance(palette[foreground]), luminance(palette[background])) + 0.05) / (Math.min(luminance(palette[foreground]), luminance(palette[background])) + 0.05);
				expect(ratio, `${selector} ${foreground}/${background}`).toBeGreaterThanOrEqual(4.5);
			}
		}
	});
});
