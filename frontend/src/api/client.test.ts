import { AxiosError, type AxiosAdapter, type AxiosInstance } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuthAdapter, RetryableRequestConfig } from "./authAdapter";
import { createApiClient, getApiClient } from "./client";
import { ApiError } from "./errors";

function createAdapter(overrides: Partial<AuthAdapter> = {}): AuthAdapter {
	const adapter = {
		mode: "session" as const,
		attach: vi.fn((config) => ({ ...config, withCredentials: true })),
		onLoginSuccess: vi.fn(),
		onUnauthorized: vi.fn().mockResolvedValue(false),
		restoreSession: vi.fn().mockResolvedValue(true),
		...overrides,
		onLogout: overrides.onLogout ?? vi.fn(),
		logout: vi.fn().mockResolvedValue(undefined),
	};
	return adapter;
}

function createError(config: RetryableRequestConfig, status: number, data: unknown): AxiosError {
	return new AxiosError("Request failed", "ERR_BAD_REQUEST", config as never, undefined, {
		data,
		status,
		statusText: "",
		headers: {},
		config: config as never,
	});
}

function withAdapter(adapter: AuthAdapter, httpAdapter: AxiosAdapter): AxiosInstance {
	const client = createApiClient({ authAdapter: adapter, onLogout: vi.fn() });
	client.defaults.adapter = httpAdapter;
	return client;
}

describe("createApiClient", () => {
	afterEach(() => {
		vi.unstubAllEnvs();
		vi.resetModules();
	});

	it("baseURL、timeout、Cookie送信設定を共有する", async () => {
		vi.stubEnv("VITE_API_BASE_URL", "/api");
		const adapter = createAdapter();
		let requestConfig: RetryableRequestConfig | undefined;
		const client = withAdapter(adapter, async (config) => {
			requestConfig = config as RetryableRequestConfig;
			return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
		});

		await client.get("/projects");

		expect(client.defaults.baseURL).toBe("/api");
		expect(client.defaults.timeout).toBe(10000);
		expect(requestConfig?.withCredentials).toBe(true);
		expect(adapter.attach).toHaveBeenCalledOnce();
	});

	it("ログイン成功レスポンスをadapterへ委譲する", async () => {
		const adapter = createAdapter();
		const client = withAdapter(adapter, async (config) => ({
			data: { access_token: "access-token" }, status: 200, statusText: "OK", headers: {}, config,
		}));

		await client.post("/auth/login", { identifier: "taro", password: "password" });

		expect(adapter.onLoginSuccess).toHaveBeenCalledWith({ access_token: "access-token" });
	});

	it("401をadapterのrefresh成功後に1回だけ再送する", async () => {
		const adapter = createAdapter({ onUnauthorized: vi.fn().mockResolvedValue(true) });
		let count = 0;
		const client = withAdapter(adapter, async (config) => {
			count += 1;
			if (count === 1) {
				throw createError(config as RetryableRequestConfig, 401, { error: { code: "TOKEN_EXPIRED", message: "期限切れ" } });
			}
			return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
		});

		expect((await client.get("/projects")).data).toEqual({ ok: true });
		expect(count).toBe(2);
		expect(adapter.onUnauthorized).toHaveBeenCalledOnce();
		expect(adapter.onLogout).not.toHaveBeenCalled();
	});

	it("401のrefresh失敗時はadapterとlogout callbackへ委譲しApiErrorにする", async () => {
		const adapter = createAdapter();
		const onLogout = vi.fn();
		const client = createApiClient({ authAdapter: adapter, onLogout });
		client.defaults.adapter = async (config) => {
			throw createError(config as RetryableRequestConfig, 401, {
				error: { code: "UNAUTHENTICATED", message: "認証が必要です", details: null, request_id: "req-1" },
			});
		};

		await expect(client.get("/projects")).rejects.toBeInstanceOf(ApiError);
		expect(adapter.onLogout).toHaveBeenCalledOnce();
		expect(onLogout).toHaveBeenCalledOnce();
	});

	it.each([403, 409, 422, 500, 503])("%iをApiErrorへ変換する", async (status) => {
		const adapter = createAdapter();
		const code = status === 403 ? "FORBIDDEN" : status === 409 ? "TASK_CONFLICT" : status === 422 ? "VALIDATION_ERROR" : status === 503 ? "SERVICE_UNAVAILABLE" : "INTERNAL_ERROR";
		const client = withAdapter(adapter, async (config) => {
			throw createError(config as RetryableRequestConfig, status, { error: { code, message: "失敗", details: null } });
		});

		await expect(client.get("/resource")).rejects.toMatchObject({ code, status });
		expect(adapter.onLogout).not.toHaveBeenCalled();
	});

	it("REFRESH_EXEMPT_PATHSと前方一致するだけの別パスはexempt対象にせずlogoutを実行する", async () => {
		const adapter = createAdapter();
		const onLogout = vi.fn();
		const client = createApiClient({ authAdapter: adapter, onLogout });
		client.defaults.adapter = async (config) => {
			throw createError(config as RetryableRequestConfig, 401, {
				error: { code: "UNAUTHENTICATED", message: "認証が必要です", details: null, request_id: "req-2" },
			});
		};

		await expect(client.get("/auth/login-history")).rejects.toBeInstanceOf(ApiError);
		expect(adapter.onLogout).toHaveBeenCalledOnce();
		expect(onLogout).toHaveBeenCalledOnce();
	});

	it("LOGIN_SUCCESS_PATHSと前方一致するだけの別パスではonLoginSuccessを呼ばない", async () => {
		const adapter = createAdapter();
		const client = withAdapter(adapter, async (config) => ({
			data: { access_token: "access-token" }, status: 200, statusText: "OK", headers: {}, config,
		}));

		await client.post("/auth/login-history", { taskId: "1" });

		expect(adapter.onLoginSuccess).not.toHaveBeenCalled();
	});
});

describe("getApiClient", () => {
	it("同一モジュール内では共有インスタンスを返す", () => {
		vi.stubEnv("VITE_API_BASE_URL", "/api");

		expect(getApiClient()).toBe(getApiClient());
	});
});
