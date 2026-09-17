import { describe, expect, it } from "vitest";

import { projectCreateSchema } from "./validation";

describe("プロジェクト説明文の長さ", () => {
	it("絵文字をUnicodeコードポイントで数える", () => {
		const base = { name: "プロジェクト" };

		expect(projectCreateSchema.safeParse({ ...base, description: "😀".repeat(2000) }).success).toBe(true);
		expect(projectCreateSchema.safeParse({ ...base, description: "😀".repeat(2001) }).success).toBe(false);
	});
});
