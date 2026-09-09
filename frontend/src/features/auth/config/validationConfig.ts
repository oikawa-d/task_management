/**
 * パスワードポリシーの最小文字数を環境変数から取得する。
 * `basic_design/04_api.md` §3.1 registerのpassword制約とフロント（zod）を一致させるための設定値。
 * ハードコーディングを避けるため環境変数化し、未設定時のみ既定値を使う。
 */
const DEFAULT_PASSWORD_MIN_LENGTH = 8;

export interface AuthValidationConfig {
	passwordMinLength: number;
}

export function getAuthValidationConfig(env: ImportMetaEnv = import.meta.env): AuthValidationConfig {
	return {
		passwordMinLength: readPositiveInteger(env.VITE_PASSWORD_MIN_LENGTH, DEFAULT_PASSWORD_MIN_LENGTH),
	};
}

function readPositiveInteger(value: string | undefined, fallback: number): number {
	const parsed = Number(value);
	return value && Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
