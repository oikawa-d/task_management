import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const tokenCss = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

const css = tokenCss;

/**
 * CSS本文から指定セレクターの宣言ブロックを抜き出す。
 * @param selector 抽出対象のCSSセレクター。
 * @returns セレクター内の宣言本文。該当しない場合は空文字列。
 * @副作用 CSS本文を読み取るが、外部状態を変更しない。
 * @throws 正規表現処理自体では例外を送出しない。
 */
function block(selector: string): string {
	const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	return css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\n\\}`, "m"))?.[1] ?? "";
}

/**
 * CSS宣言ブロックから色トークンを名前と値のmapへ変換する。
 * @param source 色トークン宣言を含むCSS本文。
 * @returns 色トークン名をキー、trim済み値を値とするmap。
 * @副作用 入力文字列を読み取るが、外部状態を変更しない。
 * @throws 正規表現処理自体では例外を送出しない。
 */
function colors(source: string): Record<string, string> {
	return Object.fromEntries([...source.matchAll(/(--color-[\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]));
}

/**
 * rgb形式の色値から相対輝度を計算する。
 * @param value CSSのrgb色値。
 * @returns WCAG計算に用いる相対輝度。
 * @副作用 なし。
 * @throws rgb形式でない値を受け取った場合にErrorを送出する。
 */
function luminance(value: string): number {
	const parts = value.match(/rgb\(\s*(\d+)\s+(\d+)\s+(\d+)/);
	if (!parts) throw new Error(`Unsupported token color: ${value}`);
	const channels = parts.slice(1, 4).map((part) => Number(part) / 255).map((channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
	return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

describe("アクセシビリティ契約", () => {
	/**
	 * light/darkの主要色が存在し、WCAG AAのコントラスト比を満たすことを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 token CSS本文を読み取るが、ファイルは変更しない。
	 * @throws 色欠落またはコントラスト不足時にVitestのアサーション例外を送出する。
	 */
	it("light/darkの主要な文字色と背景色がWCAG AAを満たす", () => {
		expect(css.length).toBeGreaterThan(100);
		const pairs = [["--color-text-primary", "--color-page"], ["--color-text-primary", "--color-surface"], ["--color-text-secondary", "--color-surface"], ["--color-text-tertiary", "--color-surface"], ["--color-muted", "--color-surface"], ["--color-accent-strong", "--color-page"], ["--color-accent-strong", "--color-accent-surface"], ["--color-danger-fg", "--color-danger-surface"], ["--color-success", "--color-success-surface"], ["--color-warning", "--color-warning-surface"], ["--color-focus", "--color-surface"], ["--color-header-fg", "--color-header-bg"]];
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
