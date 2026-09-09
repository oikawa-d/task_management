import { describe, expect, it } from "vitest";

import { getValidationConfig } from "./validationConfig";

describe("getValidationConfig", () => {
	it("環境変数の値を正の整数として読み取る", () => {
		expect(getValidationConfig({ VITE_USER_NAME_MAX_LENGTH: "40", VITE_PASSWORD_MIN_LENGTH: "12" } as ImportMetaEnv)).toEqual({
			userNameMaxLength: 40,
			passwordMinLength: 12,
		});
	});

	it("未設定・不正値は設計上の既定値へ戻す", () => {
		expect(getValidationConfig({ VITE_USER_NAME_MAX_LENGTH: "0", VITE_PASSWORD_MIN_LENGTH: "invalid" } as ImportMetaEnv)).toEqual({
			userNameMaxLength: 30,
			passwordMinLength: 8,
		});
	});
});
