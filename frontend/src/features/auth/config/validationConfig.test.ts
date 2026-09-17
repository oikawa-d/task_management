import { describe, expect, it } from "vitest";

import { getAuthValidationConfig } from "./validationConfig";

describe("getAuthValidationConfig", () => {
	it("認証入力の上限を環境変数から読み取る", () => {
		expect(getAuthValidationConfig({
			VITE_USER_NAME_MAX_LENGTH: "40",
			VITE_PASSWORD_MIN_LENGTH: "12",
			VITE_PASSWORD_MAX_LENGTH: "128",
			VITE_AUTH_TOKEN_MAX_LENGTH: "512",
		} as ImportMetaEnv)).toEqual({
			userNameMaxLength: 40,
			passwordMinLength: 12,
			passwordMaxLength: 128,
			authTokenMaxLength: 512,
		});
	});

	it("未設定・不正な上限は既定値へ戻す", () => {
		expect(getAuthValidationConfig({
			VITE_PASSWORD_MAX_LENGTH: "7",
			VITE_AUTH_TOKEN_MAX_LENGTH: "42",
		} as ImportMetaEnv)).toMatchObject({
			passwordMaxLength: 128,
			authTokenMaxLength: 512,
		});
	});

	it("最小境界値を受け入れる", () => {
		expect(getAuthValidationConfig({
			VITE_PASSWORD_MAX_LENGTH: "8",
			VITE_AUTH_TOKEN_MAX_LENGTH: "43",
		} as ImportMetaEnv)).toMatchObject({
			passwordMaxLength: 8,
			authTokenMaxLength: 43,
		});
	});
});
