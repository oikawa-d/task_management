import type { ApiFieldError, PasswordChangeInput, ProfileFormValues } from "./types";

const MAX_NAME_LENGTH = 30;
const MIN_PASSWORD_LENGTH = 8;
const KANA_PATTERN = /^[ぁ-んァ-ヶー0-9]+$/;

export type ProfileField = keyof ProfileFormValues;
export type PasswordField = keyof PasswordChangeInput;

export function validateProfile(values: ProfileFormValues): Partial<Record<ProfileField, string>> {
	const errors: Partial<Record<ProfileField, string>> = {};
	const requiredFields: ProfileField[] = [
		"last_name",
		"first_name",
		"last_name_kana",
		"first_name_kana",
		"birth_date",
	];

	for (const field of requiredFields) {
		if (!values[field]?.trim()) {
			errors[field] = "入力してください";
		}
	}

	for (const field of ["last_name", "first_name"] as const) {
		const value = values[field];
		if (value && value.length > MAX_NAME_LENGTH) {
			errors[field] = "30文字以内で入力してください";
		}
	}

	for (const field of ["last_name_kana", "first_name_kana"] as const) {
		const value = values[field];
		if (value && (value.length > MAX_NAME_LENGTH || !KANA_PATTERN.test(value))) {
			errors[field] = "ひらがな・カタカナ・数字のみで入力してください";
		}
	}

	if (values.birth_date && values.birth_date > getToday()) {
		errors.birth_date = "未来の日付は指定できません";
	}

	return errors;
}

export function validatePassword(
	values: PasswordChangeInput,
	hasPassword: boolean,
): Partial<Record<PasswordField, string>> {
	const errors: Partial<Record<PasswordField, string>> = {};
	if (hasPassword && !values.current_password) {
		errors.current_password = "現在のパスワードを入力してください";
	}

	if (!hasPassword && values.current_password) {
		errors.current_password = "現在のパスワードは送信できません";
	}

	if (
		values.new_password.length < MIN_PASSWORD_LENGTH ||
		countCharacterTypes(values.new_password) < 2
	) {
		errors.new_password = "8文字以上で、2種類以上の文字種を含めてください";
	}
	if (values.new_password !== values.password_confirm) {
		errors.password_confirm = "新しいパスワードが一致しません";
	}

	return errors;
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
	const payload = getApiErrorPayload(error);
	if (!payload || !Array.isArray(payload.details)) {
		return [];
	}

	return payload.details.filter(isApiFieldError).map((detail) => ({
		...detail,
		field: normalizeApiField(detail.field),
	}));
}

export function getApiErrorCode(error: unknown): string | undefined {
	return getApiErrorPayload(error)?.code;
}

interface ApiErrorPayload {
	code?: string;
	details?: unknown;
}

function getApiErrorPayload(error: unknown): ApiErrorPayload | undefined {
	if (!error || typeof error !== "object") {
		return undefined;
	}

	const candidate = error as Record<string, unknown>;
	const payload = candidate.error && typeof candidate.error === "object"
		? candidate.error as Record<string, unknown>
		: candidate;

	return {
		code: typeof payload.code === "string" ? payload.code : undefined,
		details: payload.details,
	};
}

function normalizeApiField(field: string): string {
	return field.startsWith("body.") ? field.slice("body.".length) : field;
}
