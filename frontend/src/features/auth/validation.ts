import { z } from "zod";
import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";

import { getAuthValidationConfig } from "./config/validationConfig";
import type { ApiFieldError } from "./types";

const EMAIL_MAX_LENGTH = 50;

/**
 * zodスキーマをreact-hook-formのResolverへ変換する。
 * 参照: frontend/src/features/settings/validation.ts（同一パターンを流用）
 */
export function createZodResolver<T extends FieldValues>(schema: z.ZodType<T>): Resolver<T> {
	return async (values) => {
		const result = schema.safeParse(values);
		if (result.success) {
			return { values: result.data, errors: {} };
		}

		const errors: FieldErrors<T> = {};
		for (const issue of result.error.issues) {
			const field = issue.path[0];
			if (typeof field === "string") {
				(errors as Record<string, unknown>)[field] = { type: issue.code, message: issue.message };
			}
		}
		return { values: {}, errors };
	};
}

/** docs/detailed_design/screen/03_password_forgot.md §10 */
export const passwordForgotSchema = z.object({
	email: z.string().email("メールアドレスの形式が正しくありません").max(EMAIL_MAX_LENGTH, "メールアドレスの形式が正しくありません"),
});

/** docs/detailed_design/screen/04_password_reset.md §10 */
export function passwordResetSchema() {
	const minLength = getAuthValidationConfig().passwordMinLength;
	return z.object({
		newPassword: z.string().refine(
			(value) => value.length >= minLength && countCharacterTypes(value) >= 2,
			`${minLength}文字以上で、2種類以上の文字種を含めてください`,
		),
		passwordConfirm: z.string(),
	}).superRefine((values, context) => {
		if (values.newPassword !== values.passwordConfirm) {
			context.addIssue({
				code: z.ZodIssueCode.custom,
				path: ["passwordConfirm"],
				message: "パスワードが一致しません",
			});
		}
	});
}

/** docs/detailed_design/screen/05_verify_email.md §10 */
export const resendVerificationSchema = z.object({
	email: z.string().email("有効なメールアドレスを入力してください").max(EMAIL_MAX_LENGTH, "有効なメールアドレスを入力してください"),
});

function countCharacterTypes(value: string): number {
	return [/[A-Z]/, /[a-z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(value)).length;
}

function isApiFieldError(value: unknown): value is ApiFieldError {
	if (!value || typeof value !== "object") {
		return false;
	}
	const candidate = value as Record<string, unknown>;
	return typeof candidate.field === "string" && typeof candidate.message === "string";
}

/** ApiErrorのdetails（422時のフィールドエラー配列）を取り出す */
export function getFieldErrors(error: unknown): ApiFieldError[] {
	if (!error || typeof error !== "object" || !("details" in error)) {
		return [];
	}
	const details = (error as { details?: unknown }).details;
	return Array.isArray(details) ? details.filter(isApiFieldError) : [];
}
