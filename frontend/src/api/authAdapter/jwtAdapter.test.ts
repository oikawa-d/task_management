import type { AxiosError, AxiosInstance } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER_NAME } from "./constants";
import { JwtAdapter } from "./jwtAdapter";
import type { RetryableRequestConfig, TokenStore } from "./types";

function createTokenStore(initial: string | null = null): TokenStore {
	let token = initial;
	return {
		getAccessToken: () => token,
		setAccessToken: (next) => {
			token = next;
		},
	};
}

function createMockHttpClient(postImpl: (..._args: unknown[]) => Promise<unknown>): AxiosInstance {
	return { post: vi.fn(postImpl) } as unknown as AxiosInstance;
}

function clearCookies(): void {
	document.cookie.split(";").forEach((cookie) => {
		const name = cookie.split("=")[0]?.trim();
		if (name) {
			document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
		}
	});
}

describe("JwtAdapter", () => {
	beforeEach(() => {
		clearCookies();
	});

	it("アクセストークン保持時は通常APIにAuthorizationヘッダを付与する", () => {
		const tokenStore = createTokenStore("access-token");
		const adapter = new JwtAdapter(tokenStore, createMockHttpClient(async () => ({ data: {} })));

		const attached = adapter.attach({ method: "get", url: "/projects" });

		expect(attached.headers?.Authorization).toBe("Bearer access-token");
		expect(attached.withCredentials).toBeUndefined();
	});

	it("refreshリクエストにはwithCredentialsとCSRFヘッダを付与しAuthorizationは付与しない", () => {
		document.cookie = "cerberus_csrf=csrf-value";
		const tokenStore = createTokenStore("access-token");
		const adapter = new JwtAdapter(tokenStore, createMockHttpClient(async () => ({ data: {} })));

		const attached = adapter.attach({ method: "post", url: "/auth/refresh" });

		expect(attached.withCredentials).toBe(true);
		expect(attached.headers?.[CSRF_HEADER_NAME]).toBe("csrf-value");
		expect(attached.headers?.Authorization).toBeUndefined();
	});

	it("onLoginSuccessでアクセストークンを保持する", () => {
		const tokenStore = createTokenStore(null);
		const adapter = new JwtAdapter(tokenStore, createMockHttpClient(async () => ({ data: {} })));

		adapter.onLoginSuccess({ access_token: "new-token" });

		expect(tokenStore.getAccessToken()).toBe("new-token");
	});

	it("リフレッシュ対象外パス（/auth/login等）の401はリトライしない", async () => {
		const httpClient = createMockHttpClient(async () => ({ data: { access_token: "x" } }));
		const adapter = new JwtAdapter(createTokenStore(), httpClient);
		const error = { config: { url: "/auth/login" } as RetryableRequestConfig } as AxiosError;

		const result = await adapter.onUnauthorized(error);

		expect(result).toBe(false);
		expect(httpClient.post).not.toHaveBeenCalled();
	});

	it("既にリトライ済み（_retried）の401は再リトライしない", async () => {
		const httpClient = createMockHttpClient(async () => ({ data: { access_token: "x" } }));
		const adapter = new JwtAdapter(createTokenStore(), httpClient);
		const error = {
			config: { url: "/projects", _retried: true } as RetryableRequestConfig,
		} as AxiosError;

		const result = await adapter.onUnauthorized(error);

		expect(result).toBe(false);
		expect(httpClient.post).not.toHaveBeenCalled();
	});

	it("refresh成功時はtrueを返し新しいアクセストークンを保持する", async () => {
		const httpClient = createMockHttpClient(async () => ({ data: { access_token: "refreshed-token" } }));
		const tokenStore = createTokenStore("old-token");
		const adapter = new JwtAdapter(tokenStore, httpClient);
		const error = { config: { url: "/projects" } as RetryableRequestConfig } as AxiosError;

		const result = await adapter.onUnauthorized(error);

		expect(result).toBe(true);
		expect(tokenStore.getAccessToken()).toBe("refreshed-token");
	});

	it("起動時のセッション復元でrefreshを実行する", async () => {
		const httpClient = createMockHttpClient(async () => ({ data: { access_token: "restored-token" } }));
		const tokenStore = createTokenStore();
		const adapter = new JwtAdapter(tokenStore, httpClient);

		expect(await adapter.restoreSession()).toBe(true);
		expect(tokenStore.getAccessToken()).toBe("restored-token");
		expect(httpClient.post).toHaveBeenCalledTimes(1);
	});

	it("refresh失敗時はfalseを返しアクセストークンを破棄する", async () => {
		const httpClient = createMockHttpClient(async () => {
			throw new Error("refresh failed");
		});
		const tokenStore = createTokenStore("old-token");
		const adapter = new JwtAdapter(tokenStore, httpClient);
		const error = { config: { url: "/projects" } as RetryableRequestConfig } as AxiosError;

		const result = await adapter.onUnauthorized(error);

		expect(result).toBe(false);
		expect(tokenStore.getAccessToken()).toBeNull();
	});

	it("同時に発生した複数の401は1回のリフレッシュに集約される（多重実行防止）", async () => {
		let resolveRefresh: (value: { data: { access_token: string } }) => void = () => {};
		const refreshPromise = new Promise((resolve) => {
			resolveRefresh = resolve;
		});
		const httpClient = createMockHttpClient(() => refreshPromise as Promise<unknown>);
		const adapter = new JwtAdapter(createTokenStore(), httpClient);
		const errorA = { config: { url: "/projects" } as RetryableRequestConfig } as AxiosError;
		const errorB = { config: { url: "/tasks/1" } as RetryableRequestConfig } as AxiosError;

		const resultAPromise = adapter.onUnauthorized(errorA);
		const resultBPromise = adapter.onUnauthorized(errorB);
		resolveRefresh({ data: { access_token: "shared-token" } });
		const [resultA, resultB] = await Promise.all([resultAPromise, resultBPromise]);

		expect(resultA).toBe(true);
		expect(resultB).toBe(true);
		expect(httpClient.post).toHaveBeenCalledTimes(1);
	});

	it("onLogoutでアクセストークンをメモリから破棄する", () => {
		const tokenStore = createTokenStore("access-token");
		const adapter = new JwtAdapter(tokenStore, createMockHttpClient(async () => ({ data: {} })));

		adapter.onLogout();

		expect(tokenStore.getAccessToken()).toBeNull();
	});
});
