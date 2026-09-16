import { z } from "zod";
import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";

import { getValidationConfig } from "./config/validationConfig";
import type { ApiFieldError } from "./types";

const KANA_PATTERN = /^[ぁ-んァ-ヶー0-9]+$/;

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

export const profileSchema = z.object({
	last_name: nameSchema(),
	first_name: nameSchema(),
	last_name_kana: kanaSchema(),
	first_name_kana: kanaSchema(),
	birth_date: z.string().min(1, "入力してください").refine(
		(value) => value <= getToday(),
		"未来の日付は指定できません",
	),
});

export function passwordSchema(hasPassword: boolean) {
	const minLength = getValidationConfig().passwordMinLength;
	return z.object({
		current_password: hasPassword
			? z.string().min(1, "現在のパスワードを入力してください")
			: z.string().optional(),
		new_password: z.string().refine(
			(value) => value.length >= minLength && countCharacterTypes(value) >= 2,
			`${minLength}文字以上で、2種類以上の文字種を含めてください`,
		),
		password_confirm: z.string(),
	}).superRefine((values, context) => {
		if (values.new_password !== values.password_confirm) {
			context.addIssue({
				code: z.ZodIssueCode.custom,
				path: ["password_confirm"],
				message: "新しいパスワードが一致しません",
			});
		}
	});
}

function nameSchema() {
	const maxLength = getValidationConfig().userNameMaxLength;
	return z.string().trim().min(1, "入力してください").max(
		maxLength,
		`${maxLength}文字以内で入力してください`,
	);
}

function kanaSchema() {
	return nameSchema().regex(KANA_PATTERN, "ひらがな・カタカナ・数字のみで入力してください");
}

export function getToday(): string {
	const today = new Date();
	const month = String(today.getMonth() + 1).padStart(2, "0");
	const day = String(today.getDate()).padStart(2, "0");
	return `${today.getFullYear()}-${month}-${day}`;
}

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

export function getFieldErrors(error: unknown): ApiFieldError[] {
	if (!error || typeof error !== "object" || !("details" in error)) {
		return [];
	}

	const details = (error as { details?: unknown }).details;
	return Array.isArray(details) ? details.filter(isApiFieldError) : [];
}
