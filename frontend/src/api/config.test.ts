import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiClientConfig } from "./config";

describe("getApiClientConfig", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
	});

	it("VITE_API_BASE_URLをbaseURLとして返す", () => {
		vi.stubEnv("VITE_API_BASE_URL", "/api");

		expect(getApiClientConfig()).toEqual({
			baseURL: "/api",
			timeoutMs: 10000,
		});
	});

	it("VITE_API_BASE_URLが未設定の場合はエラーを投げる", () => {
		vi.stubEnv("VITE_API_BASE_URL", "");

		expect(() => getApiClientConfig()).toThrow("VITE_API_BASE_URL が設定されていません");
	});
});
