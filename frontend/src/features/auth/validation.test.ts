import { describe, expect, it } from "vitest";

import { emailSchema, loginSchema, passwordForgotSchema, resendVerificationSchema } from "./validation";

function emailOfLength(length: number): string {
	const domainMiddleLength = length - 197;
	return `${"a".repeat(64)}@${"a".repeat(63)}.${"b".repeat(63)}.${"c".repeat(domainMiddleLength)}.com`;
}

describe("メールアドレスの上限", () => {
	it.each([
		["emailSchema", (email: string) => emailSchema.safeParse(email)],
		["loginSchema", (email: string) => loginSchema.safeParse({ identifier: email, password: "Password1" })],
		["resendVerificationSchema", (email: string) => resendVerificationSchema.safeParse({ email })],
		["passwordForgotSchema", (email: string) => passwordForgotSchema.safeParse({ email })],
	])("%sは254文字を受け入れる", (_name, parse) => {
		expect(parse(emailOfLength(254)).success).toBe(true);
	});

	it.each([
		["emailSchema", (email: string) => emailSchema.safeParse(email)],
		["loginSchema", (email: string) => loginSchema.safeParse({ identifier: email, password: "Password1" })],
		["resendVerificationSchema", (email: string) => resendVerificationSchema.safeParse({ email })],
		["passwordForgotSchema", (email: string) => passwordForgotSchema.safeParse({ email })],
	])("%sは255文字を拒否する", (_name, parse) => {
		expect(parse(emailOfLength(255)).success).toBe(false);
	});
});
