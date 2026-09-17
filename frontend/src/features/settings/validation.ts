import { z } from "zod";
import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";

import { countCodePoints } from "../../lib/validation/stringLength";
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
	const { passwordMinLength, passwordMaxLength } = getValidationConfig();
	return z.object({
		current_password: hasPassword
			? passwordField("現在のパスワードを入力してください", passwordMaxLength)
			: z.string().optional(),
		new_password: z.string().refine(
			(value) => countCodePoints(value) >= passwordMinLength && countCharacterTypes(value) >= 2,
			`${passwordMinLength}文字以上で、2種類以上の文字種を含めてください`,
		).refine(
			(value) => countCodePoints(value) <= passwordMaxLength,
			`${passwordMaxLength}文字以内で入力してください`,
		),
		password_confirm: passwordField(undefined, passwordMaxLength),
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

function passwordField(requiredMessage: string | undefined, maxLength: number): z.ZodType<string> {
	let schema = z.string();
	if (requiredMessage) {
		schema = schema.min(1, requiredMessage);
	}
	return schema.refine((value) => countCodePoints(value) <= maxLength, `${maxLength}文字以内で入力してください`);
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
