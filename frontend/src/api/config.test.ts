import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_API_BASE_URL } from "./authAdapter/constants";
import { getApiClientConfig } from "./config";

describe("getApiClientConfig", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
	});

	it("APIベースURLを環境変数から読み取り、既定タイムアウトを返す", () => {
		vi.stubEnv("VITE_API_BASE_URL", "/backend-api");

		expect(getApiClientConfig()).toEqual({ baseURL: "/backend-api", timeoutMs: 10000 });
	});

	it("未設定時は設計書の同一オリジンURLと既定タイムアウトを使う", () => {
		vi.stubEnv("VITE_API_BASE_URL", "");

		expect(getApiClientConfig()).toEqual({ baseURL: DEFAULT_API_BASE_URL, timeoutMs: 10000 });
	});
});
