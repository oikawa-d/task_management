import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER_NAME } from "./constants";
import { clearAuthAdapter, fetchWithAuth, setAuthAccessToken } from "./client";

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

	it("/auth/configのauth_modeを実行時に読み取りJWTのBearerを付与する", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce(response({ auth_mode: "jwt" }, { ok: true, status: 200 }))
			.mockResolvedValueOnce(response({ columns: {} }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);
		setAuthAccessToken("access-token");

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/auth/config", expect.objectContaining({ method: "GET" }));
		const [, requestInit] = fetchMock.mock.calls[1] as [string, RequestInit];
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
