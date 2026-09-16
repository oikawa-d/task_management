/**
 * design doc: docs/basic_design/05_frontend.md §3.9 環境変数一覧
 * 認証入力の上限・下限はbackendの同名設定と一致させる。
 */
const DEFAULT_USER_NAME_MAX_LENGTH = 30;
const DEFAULT_PASSWORD_MIN_LENGTH = 8;
const DEFAULT_PASSWORD_MAX_LENGTH = 128;
const DEFAULT_AUTH_TOKEN_MAX_LENGTH = 512;

export interface AuthValidationConfig {
	userNameMaxLength: number;
	passwordMinLength: number;
	passwordMaxLength: number;
	authTokenMaxLength: number;
}

export function getAuthValidationConfig(env: ImportMetaEnv = import.meta.env): AuthValidationConfig {
	return {
		userNameMaxLength: readPositiveInteger(env.VITE_USER_NAME_MAX_LENGTH, DEFAULT_USER_NAME_MAX_LENGTH),
		passwordMinLength: readPositiveInteger(env.VITE_PASSWORD_MIN_LENGTH, DEFAULT_PASSWORD_MIN_LENGTH),
		passwordMaxLength: readPositiveInteger(env.VITE_PASSWORD_MAX_LENGTH, DEFAULT_PASSWORD_MAX_LENGTH),
		authTokenMaxLength: readPositiveInteger(env.VITE_AUTH_TOKEN_MAX_LENGTH, DEFAULT_AUTH_TOKEN_MAX_LENGTH),
	};
}

function readPositiveInteger(value: string | undefined, fallback: number): number {
	const parsed = Number(value);
	return value && Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
