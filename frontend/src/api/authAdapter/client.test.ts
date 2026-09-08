import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER_NAME } from "./constants";
import { clearAuthAdapter, fetchWithAuth, setAuthAdapter, setAuthAdapterMode } from "./client";
import { JwtAdapter } from "./jwtAdapter";

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

	it("設定済みJWTアダプタでBearerを付与する", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response({ columns: {} }, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);
		const adapter = new JwtAdapter();
		adapter.onLoginSuccess({ access_token: "access-token" });
		setAuthAdapter(adapter);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		const [requestUrl, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(requestUrl).toBe("/api/projects");
		expect(new Headers(requestInit.headers).get("Authorization")).toBe("Bearer access-token");
		expect(requestInit.credentials).toBe("same-origin");
	});

	it("sessionモードの更新系にはCSRFを付与する", async () => {
		document.cookie = "cerberus_csrf=csrf-token";
		const fetchMock = vi.fn().mockResolvedValue(response({}, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);
		setAuthAdapterMode("session");

		await fetchWithAuth("/api/tasks/1", { method: "PATCH" }, "/api");

		const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(new Headers(requestInit.headers).get(CSRF_HEADER_NAME)).toBe("csrf-token");
		expect(requestInit.credentials).toBe("include");
	});

	it("sessionモードのGETにはCSRFを付与しない", async () => {
		document.cookie = "cerberus_csrf=csrf-token";
		const fetchMock = vi.fn().mockResolvedValue(response({}, { ok: true, status: 200 }));
		vi.stubGlobal("fetch", fetchMock);
		setAuthAdapterMode("session");

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(new Headers(requestInit.headers).has(CSRF_HEADER_NAME)).toBe(false);
	});
});
