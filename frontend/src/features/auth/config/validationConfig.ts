/**
 * design doc: docs/basic_design/05_frontend.md §3.9 環境変数一覧
 * ここで参照する2変数は姓名・フリガナ（VITE_USER_NAME_MAX_LENGTH）、パスワード（VITE_PASSWORD_MIN_LENGTH）の
 * zodバリデーション上限/下限として設計書に列挙済みのもの。ここで新規のVITE_変数は追加しない。
 */
const DEFAULT_USER_NAME_MAX_LENGTH = 30;
const DEFAULT_PASSWORD_MIN_LENGTH = 8;

export interface AuthValidationConfig {
	userNameMaxLength: number;
	passwordMinLength: number;
}

export function getAuthValidationConfig(env: ImportMetaEnv = import.meta.env): AuthValidationConfig {
	return {
		userNameMaxLength: readPositiveInteger(env.VITE_USER_NAME_MAX_LENGTH, DEFAULT_USER_NAME_MAX_LENGTH),
		passwordMinLength: readPositiveInteger(env.VITE_PASSWORD_MIN_LENGTH, DEFAULT_PASSWORD_MIN_LENGTH),
	};
}

function readPositiveInteger(value: string | undefined, fallback: number): number {
	const parsed = Number(value);
	return value && Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
