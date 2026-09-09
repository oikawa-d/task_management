import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createAuthAdapter } from "./index";
import { CSRF_HEADER_NAME } from "./constants";
import { clearAuthAdapter, fetchWithAuth, setAuthAdapter } from "./client";

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
});
