import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createAuthAdapter } from "./index";
import { CSRF_HEADER_NAME } from "./constants";
import { clearAuthAdapter, fetchWithAuth, resolveAuthAdapter, setAuthAccessToken, setAuthAdapter } from "./client";

function response(body: unknown, init: { ok: boolean; status: number }) {
	return {
		...init,
		json: vi.fn().mockResolvedValue(body),
	};
}

describe("fetchWithAuth", () => {
	beforeEach(() => {
		clearAuthAdapter();
		document.cookie = "cerberus_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it("bootstrap未実行のときは/auth/configのauth_modeを実行時に読み取る", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce(response({ auth_mode: "jwt" }, { ok: true, status: 200 }))
			.mockResolvedValueOnce(response({ columns: {} }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/auth/config", expect.objectContaining({ method: "GET" }));
		const [, requestInit] = fetchMock.mock.calls[1] as [string, RequestInit];
		expect(requestInit.credentials).toBe("same-origin");
	});

	it("setAuthAdapterで登録したアダプタのトークンでBearerを付与する", async () => {
		let accessToken: string | null = null;
		const adapter = createAuthAdapter("jwt", {
			tokenStore: {
				getAccessToken: () => accessToken,
				setAccessToken: (token) => {
					accessToken = token;
				},
			},
		});
		adapter.onLoginSuccess({ access_token: "access-token" });
		setAuthAdapter(adapter);

		const fetchMock = vi.fn().mockResolvedValue(response({ columns: {} }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		expect(fetchMock).toHaveBeenCalledOnce();
		const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(url).toBe("/api/projects");
		expect(new Headers(requestInit.headers).get("Authorization")).toBe("Bearer access-token");
		expect(requestInit.credentials).toBe("same-origin");
	});

	it("sessionモードの更新系にはCSRFを付与する", async () => {
		document.cookie = "cerberus_csrf=csrf-token";
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce(response({ auth_mode: "session" }, { ok: true, status: 200 }))
			.mockResolvedValueOnce(response({}, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/tasks/1", { method: "PATCH" }, "/api");

		const [, requestInit] = fetchMock.mock.calls[1] as [string, RequestInit];
		expect(new Headers(requestInit.headers).get(CSRF_HEADER_NAME)).toBe("csrf-token");
		expect(requestInit.credentials).toBe("include");
	});

	it("sessionモードのGETにはCSRFを付与しない", async () => {
		document.cookie = "cerberus_csrf=csrf-token";
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce(response({ auth_mode: "session" }, { ok: true, status: 200 }))
			.mockResolvedValueOnce(response({}, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		const [, requestInit] = fetchMock.mock.calls[1] as [string, RequestInit];
		expect(new Headers(requestInit.headers).has(CSRF_HEADER_NAME)).toBe(false);
	});

	it("resolveAuthAdapter開始後にbootstrapAuthが先に共有アダプタを登録した場合、先行/auth/configの完了で上書きされない", async () => {
		let resolveConfigRequest!: (value: unknown) => void;
		const configRequestPromise = new Promise((resolve) => {
			resolveConfigRequest = resolve;
		});
		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url === "/api/auth/config") {
				return configRequestPromise;
			}
			return Promise.resolve(response({ columns: {} }, { ok: true, status: 200 }));
		});
		vi.stubGlobal("fetch", fetchMock);

		// 1. resolveAuthAdapter()を先行開始する（/auth/configはpendingのまま）
		const resolvePromise = resolveAuthAdapter("/api");

		// 2. bootstrapAuth()相当の処理が先に共有アダプタAを登録する
		let accessToken: string | null = "bootstrap-token";
		const bootstrapAdapter = createAuthAdapter("jwt", {
			tokenStore: {
				getAccessToken: () => accessToken,
				setAccessToken: (token) => {
					accessToken = token;
				},
			},
		});
		setAuthAdapter(bootstrapAdapter);

		// 3. 先行していた/auth/configリクエストが完了し、.then()が発火する
		resolveConfigRequest(response({ auth_mode: "jwt" }, { ok: true, status: 200 }));

		const resolvedAdapter = await resolvePromise;

		// fallback生成で上書きされず、bootstrapAuth()が登録したアダプタが維持される
		expect(resolvedAdapter).toBe(bootstrapAdapter);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");
		const [, requestInit] = fetchMock.mock.calls[1] as [string, RequestInit];
		expect(new Headers(requestInit.headers).get("Authorization")).toBe("Bearer bootstrap-token");
	});

	it("アダプタ未登録時にsetAuthAccessTokenを呼んでも破棄されず、setAuthAdapterでの登録時に反映される", async () => {
		// アダプタ未登録（OAuthハンドオフ交換がbootstrapAuth()完了より先に成功するケース）
		setAuthAccessToken("oauth-token");

		let accessToken: string | null = null;
		const adapter = createAuthAdapter("jwt", {
			tokenStore: {
				getAccessToken: () => accessToken,
				setAccessToken: (token) => {
					accessToken = token;
				},
			},
		});
		setAuthAdapter(adapter);

		const fetchMock = vi.fn().mockResolvedValue(response({ columns: {} }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(new Headers(requestInit.headers).get("Authorization")).toBe("Bearer oauth-token");
	});

	it("setAuthAccessTokenにnullを渡すと登録済みアダプタのトークンをクリアする", async () => {
		let accessToken: string | null = "existing-token";
		const adapter = createAuthAdapter("jwt", {
			tokenStore: {
				getAccessToken: () => accessToken,
				setAccessToken: (token) => {
					accessToken = token;
				},
			},
		});
		setAuthAdapter(adapter);

		setAuthAccessToken(null);
		expect(accessToken).toBeNull();

		const fetchMock = vi.fn().mockResolvedValue(response({ columns: {} }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(new Headers(requestInit.headers).has("Authorization")).toBe(false);
	});

	it("アダプタ未登録時にnullを渡した場合は持ち越しトークンをクリアし、後続のアダプタ登録に影響しない", async () => {
		setAuthAccessToken("stale-token");
		setAuthAccessToken(null);

		let accessToken: string | null = null;
		const adapter = createAuthAdapter("jwt", {
			tokenStore: {
				getAccessToken: () => accessToken,
				setAccessToken: (token) => {
					accessToken = token;
				},
			},
		});
		setAuthAdapter(adapter);

		expect(accessToken).toBeNull();
	});
});
