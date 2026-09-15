import { z } from "zod";
import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";

import { getAuthValidationConfig } from "./config/validationConfig";
import type { ApiFieldError, AuthApiError } from "./types";

const KANA_PATTERN = /^[ぁ-んァ-ヶー0-9]+$/;
const USERNAME_PATTERN = /^[A-Za-z0-9_-]+$/;
/** API契約（docs/detailed_design/api/auth/02_post_auth_login.md §10）に合わせる。 */
const LOGIN_IDENTIFIER_MAX_LENGTH = 50;
const EMAIL_MAX_LENGTH = 50;
const USERNAME_MIN_LENGTH = 3;
const USERNAME_MAX_LENGTH = 50;

export function createZodResolver<T extends FieldValues>(schema: z.ZodType<T>): Resolver<T> {
	return async (values) => {
		const result = schema.safeParse(values);
		if (result.success) {
			return { values: result.data, errors: {} };
		}

		const errors: FieldErrors<T> = {};
		for (const issue of result.error.issues) {
			const field = issue.path[0];
			if (typeof field === "string" && !(field in errors)) {
				(errors as Record<string, unknown>)[field] = { type: issue.code, message: issue.message };
			}
		}
		return { values: {}, errors };
	};
}

export const emailSchema = z.string().max(EMAIL_MAX_LENGTH).email();

export const loginSchema = z.object({
	identifier: z.string().min(1, "IDまたはメールアドレスを入力してください").max(LOGIN_IDENTIFIER_MAX_LENGTH),
	password: z.string().min(1, "パスワードを入力してください"),
});

export const resendVerificationSchema = z.object({
	email: z
		.string()
		.email("有効なメールアドレスを入力してください")
		.max(EMAIL_MAX_LENGTH, "有効なメールアドレスを入力してください"),
});

export function registerSchema() {
	const { userNameMaxLength, passwordMinLength } = getAuthValidationConfig();
	const nameField = z.string().trim().min(1, "入力してください").max(userNameMaxLength, `${userNameMaxLength}文字以内で入力してください`);
	const kanaField = nameField.regex(KANA_PATTERN, "ひらがな・カタカナ・数字で入力してください");

	return z
		.object({
			last_name: nameField,
			first_name: nameField,
			last_name_kana: kanaField,
			first_name_kana: kanaField,
			birth_year: z.string().min(1, "正しい生年月日を選択してください"),
			birth_month: z.string().min(1, "正しい生年月日を選択してください"),
			birth_day: z.string().min(1, "正しい生年月日を選択してください"),
			email: emailSchema,
			username: z
				.string()
				.min(USERNAME_MIN_LENGTH, `${USERNAME_MIN_LENGTH}〜${USERNAME_MAX_LENGTH}文字の英数字・ハイフン・アンダースコアで入力してください`)
				.max(USERNAME_MAX_LENGTH, `${USERNAME_MIN_LENGTH}〜${USERNAME_MAX_LENGTH}文字の英数字・ハイフン・アンダースコアで入力してください`)
				.regex(USERNAME_PATTERN, `${USERNAME_MIN_LENGTH}〜${USERNAME_MAX_LENGTH}文字の英数字・ハイフン・アンダースコアで入力してください`),
			password: z
				.string()
				.refine(
					(value) => value.length >= passwordMinLength && countCharacterTypes(value) >= 2,
					`${passwordMinLength}文字以上で、英大文字/英小文字/数字/記号のうち2種類以上を含めてください`,
				),
			password_confirm: z.string(),
		})
		.superRefine((values, context) => {
			if (values.password_confirm !== values.password) {
				context.addIssue({ code: z.ZodIssueCode.custom, path: ["password_confirm"], message: "パスワードが一致しません" });
			}
			if (!isValidBirthDate(values.birth_year, values.birth_month, values.birth_day)) {
				context.addIssue({ code: z.ZodIssueCode.custom, path: ["birth_day"], message: "正しい生年月日を選択してください" });
			}
		});
}

function isValidBirthDate(year: string, month: string, day: string): boolean {
	const y = Number(year);
	const m = Number(month);
	const d = Number(day);
	if (!Number.isInteger(y) || !Number.isInteger(m) || !Number.isInteger(d)) {
		return false;
	}
	const date = new Date(y, m - 1, d);
	const isRealDate = date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
	return isRealDate && date.getTime() <= Date.now();
}

export function countCharacterTypes(value: string): number {
	return [/[A-Z]/, /[a-z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(value)).length;
}

/** design doc: docs/detailed_design/screen/01_login.md §9.3 buildResendPayload */
export function buildResendPayload(identifier: string): { email: string } | null {
	const result = emailSchema.safeParse(identifier);
	return result.success ? { email: result.data } : null;
}

export function getErrorCode(error: unknown): string | undefined {
	if (!error || typeof error !== "object" || !("code" in error)) {
		return undefined;
	}
	const code = (error as AuthApiError).code;
	return typeof code === "string" ? code : undefined;
}

function isApiFieldError(value: unknown): value is ApiFieldError {
	if (!value || typeof value !== "object") {
		return false;
	}
	const candidate = value as Record<string, unknown>;
	return typeof candidate.field === "string" && typeof candidate.message === "string";
}

export function getFieldErrors(error: unknown): ApiFieldError[] {
	if (!error || typeof error !== "object" || !("details" in error)) {
		return [];
	}
	const details = (error as AuthApiError).details;
	return Array.isArray(details) ? details.filter(isApiFieldError) : [];
}

/** docs/detailed_design/screen/03_password_forgot.md §10 */
export const passwordForgotSchema = z.object({
	email: z
		.string()
		.email("メールアドレスの形式が正しくありません")
		.max(EMAIL_MAX_LENGTH, "メールアドレスの形式が正しくありません"),
});

/** docs/detailed_design/screen/04_password_reset.md §10 */
export function passwordResetSchema() {
	const minLength = getAuthValidationConfig().passwordMinLength;
	return z
		.object({
			newPassword: z
				.string()
				.refine(
					(value) => value.length >= minLength && countCharacterTypes(value) >= 2,
					`${minLength}文字以上で、2種類以上の文字種を含めてください`,
				),
			passwordConfirm: z.string(),
		})
		.superRefine((values, context) => {
			if (values.newPassword !== values.passwordConfirm) {
				context.addIssue({
					code: z.ZodIssueCode.custom,
					path: ["passwordConfirm"],
					message: "パスワードが一致しません",
				});
			}
		});
}
