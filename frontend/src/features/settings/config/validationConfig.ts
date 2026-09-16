const DEFAULT_USER_NAME_MAX_LENGTH = 30;
const DEFAULT_PASSWORD_MIN_LENGTH = 8;

export interface ValidationConfig {
	userNameMaxLength: number;
	passwordMinLength: number;
}

export function getValidationConfig(env: ImportMetaEnv = import.meta.env): ValidationConfig {
	return {
		userNameMaxLength: readPositiveInteger(env.VITE_USER_NAME_MAX_LENGTH, DEFAULT_USER_NAME_MAX_LENGTH),
		passwordMinLength: readPositiveInteger(env.VITE_PASSWORD_MIN_LENGTH, DEFAULT_PASSWORD_MIN_LENGTH),
	};
}

function readPositiveInteger(value: string | undefined, fallback: number): number {
	const parsed = Number(value);
	return value && Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}
