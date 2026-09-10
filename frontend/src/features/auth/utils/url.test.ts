import { describe, expect, it } from "vitest";

import { isSafeRelativePath } from "./url";

describe("isSafeRelativePath", () => {
	it("同一オリジンの相対パスを受け入れる", () => {
		expect(isSafeRelativePath("/projects/1")).toBe(true);
	});

	it("プロトコル相対URLを拒否する", () => {
		expect(isSafeRelativePath("//evil.com")).toBe(false);
	});

	it("スキーム注入を拒否する", () => {
		expect(isSafeRelativePath("javascript:alert(1)")).toBe(false);
	});

	it("先頭が/でも':'を含む場合は拒否する", () => {
		expect(isSafeRelativePath("/redirect:javascript:alert(1)")).toBe(false);
	});

	it("先頭が\\の表記を拒否する", () => {
		expect(isSafeRelativePath("/\\evil.com")).toBe(false);
	});

	it("nullを拒否する", () => {
		expect(isSafeRelativePath(null)).toBe(false);
	});

	it("undefinedを拒否する", () => {
		expect(isSafeRelativePath(undefined)).toBe(false);
	});

	it("空文字を拒否する", () => {
		expect(isSafeRelativePath("")).toBe(false);
	});

	it("/で始まらないパスを拒否する", () => {
		expect(isSafeRelativePath("dashboard")).toBe(false);
	});
});
