import axios, { type AxiosInstance } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetApiClient } from "../../../api/client";
import { getLoginHistory } from "./loginHistoryApi";

describe("loginHistoryApi", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		resetApiClient();
	});

	it("本人のログイン履歴エンドポイントを共通APIクライアントで呼ぶ", async () => {
		const client = { get: vi.fn().mockResolvedValue({ data: { items: [], meta: { limit: 50, count: 0 } } }), interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } } as unknown as AxiosInstance;
		vi.spyOn(axios, "create").mockReturnValue(client);

		await expect(getLoginHistory()).resolves.toEqual({ items: [], meta: { limit: 50, count: 0 } });
		expect(client.get).toHaveBeenCalledWith("/users/me/login-history");
	});
});
