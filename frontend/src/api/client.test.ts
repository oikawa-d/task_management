import type { AxiosAdapter } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "./client";
import { ApiError } from "./errors";

function withMockAdapter(adapter: AxiosAdapter) {
	vi.stubEnv("VITE_API_BASE_URL", "/api");
	const client = createApiClient();
	client.defaults.adapter = adapter;
	return client;
}

describe("createApiClient", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
	});

	it("VITE_API_BASE_URLをbaseURLに設定したインスタンスを生成する", () => {
		vi.stubEnv("VITE_API_BASE_URL", "/api");

		const client = createApiClient();

		expect(client.defaults.baseURL).toBe("/api");
	});

	it("成功レスポンスはそのまま返す", async () => {
		const client = withMockAdapter(async (config) => ({
			data: { ok: true },
			status: 200,
			statusText: "OK",
			headers: {},
			config,
		}));

		const response = await client.get("/tasks");

		expect(response.data).toEqual({ ok: true });
	});

	it("エラーレスポンスをApiErrorへ正規化してreject する", async () => {
		const client = withMockAdapter(async (config) => {
			const { AxiosError } = await import("axios");
			throw new AxiosError(
				"Request failed with status code 403",
				"ERR_BAD_REQUEST",
				config,
				undefined,
				{
					data: {
						error: {
							code: "PROJECT_FORBIDDEN",
							message: "このプロジェクトへのアクセス権がありません",
							details: null,
							request_id: "req-1",
						},
					},
					status: 403,
					statusText: "Forbidden",
					headers: {},
					config,
				},
			);
		});

		await expect(client.get("/projects/1")).rejects.toBeInstanceOf(ApiError);
		await expect(client.get("/projects/1")).rejects.toMatchObject({
			code: "PROJECT_FORBIDDEN",
			status: 403,
		});
	});
});

describe("getApiClient", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
		vi.resetModules();
	});

	it("同一インスタンスを返す（シングルトン）", async () => {
		vi.stubEnv("VITE_API_BASE_URL", "/api");
		vi.resetModules();
		const { getApiClient: freshGetApiClient } = await import("./client");

		expect(freshGetApiClient()).toBe(freshGetApiClient());
	});

	it("呼び出すまで環境変数未設定エラーを発生させない", async () => {
		vi.resetModules();
		const clientModule = await import("./client");

		expect(() => clientModule.getApiClient()).toThrow("VITE_API_BASE_URL が設定されていません");
	});
});
