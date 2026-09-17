import { describe, expect, it } from "vitest";

import {
	authTokenSchema,
	countCodePoints,
	emailSchema,
	loginSchema,
	oauthExchangeSchema,
	passwordForgotSchema,
	passwordResetSchema,
	registerSchema,
	resendVerificationSchema,
} from "./validation";

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

describe("認証入力の上限", () => {
	const passwordAtLimit = `A1!${"a".repeat(125)}`;
	const passwordOverLimit = `A1!${"a".repeat(126)}`;

	it("パスワードは128コードポイントを受け入れ、129コードポイントを拒否する", () => {
		const base = {
			last_name: "山田",
			first_name: "太郎",
			last_name_kana: "ヤマダ",
			first_name_kana: "タロウ",
			birth_year: "1995",
			birth_month: "04",
			birth_day: "01",
			email: "taro@example.com",
			username: "taro_01",
			password_confirm: passwordAtLimit,
		};
		expect(registerSchema().safeParse({ ...base, password: passwordAtLimit }).success).toBe(true);
		expect(registerSchema().safeParse({ ...base, password: passwordOverLimit, password_confirm: passwordOverLimit }).success).toBe(false);
		expect(passwordResetSchema().safeParse({ newPassword: passwordAtLimit, passwordConfirm: passwordAtLimit }).success).toBe(true);
		expect(passwordResetSchema().safeParse({ newPassword: passwordOverLimit, passwordConfirm: passwordOverLimit }).success).toBe(false);
	});

	it("UTF-16サロゲートペアではなくUnicodeコードポイントで数える", () => {
		const emojiPassword = "A1!" + "😀".repeat(125);
		expect(countCodePoints(emojiPassword)).toBe(128);
		expect(loginSchema.safeParse({ identifier: "taro", password: emojiPassword }).success).toBe(true);
	});

	it("token/codeは512コードポイントまで受け入れ、超過を拒否する", () => {
		expect(authTokenSchema().safeParse("a".repeat(512)).success).toBe(true);
		expect(authTokenSchema().safeParse("a".repeat(513)).success).toBe(false);
		expect(oauthExchangeSchema().safeParse({ code: "a".repeat(512) }).success).toBe(true);
		expect(oauthExchangeSchema().safeParse({ code: "a".repeat(513) }).success).toBe(false);
	});
});
