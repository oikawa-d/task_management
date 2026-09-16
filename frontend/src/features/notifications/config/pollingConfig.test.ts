import { describe, expect, it } from "vitest";

import { getNotificationPollIntervalMs } from "./pollingConfig";

function buildEnv(value: string | undefined): ImportMetaEnv {
	return {
		...import.meta.env,
		VITE_API_BASE_URL: "/api",
		VITE_NOTIFICATION_POLL_INTERVAL_MS: value as string,
	};
}

describe("getNotificationPollIntervalMs", () => {
	it("環境変数の値をそのまま数値として返す", () => {
		expect(getNotificationPollIntervalMs(buildEnv("60000"))).toBe(60000);
	});

	it("環境変数が未設定の場合は既定値(60000)を返す", () => {
		expect(getNotificationPollIntervalMs(buildEnv(undefined))).toBe(60000);
	});

	it("環境変数が空文字の場合は既定値を返す", () => {
		expect(getNotificationPollIntervalMs(buildEnv(""))).toBe(60000);
	});

	it("環境変数が数値に変換できない場合は既定値を返す", () => {
		expect(getNotificationPollIntervalMs(buildEnv("abc"))).toBe(60000);
	});

	it("環境変数が0以下の場合は既定値を返す", () => {
		expect(getNotificationPollIntervalMs(buildEnv("0"))).toBe(60000);
		expect(getNotificationPollIntervalMs(buildEnv("-100"))).toBe(60000);
	});
});
