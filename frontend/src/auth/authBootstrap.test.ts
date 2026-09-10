import axios, { type AxiosInstance } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, fetchWithAuth } from "../api/authAdapter/client";
import { AUTH_CONFIG_ENDPOINT, AUTH_ME_ENDPOINT } from "../api/authAdapter/constants";
import { resetApiClient } from "../api/client";
import { bootstrapAuth } from "./authBootstrap";

function createMockClient(authMode: "session" | "jwt"): AxiosInstance {
	return {
		get: vi
			.fn()
			.mockResolvedValueOnce({
				data: { auth_mode: authMode, google_login_enabled: false, csrf_cookie_name: "csrf" },
			})
			.mockResolvedValueOnce({ data: { id: "u1", role: "admin" } }),
		post: vi.fn().mockResolvedValue({ data: { access_token: "access-token" } }),
		interceptors: {
			request: { use: vi.fn() },
			response: { use: vi.fn() },
		},
	} as unknown as AxiosInstance;
}

describe("bootstrapAuth", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		clearAuthAdapter();
		resetApiClient();
	});

	it("gets config, restores the session, then gets the current user", async () => {
		const client = createMockClient("session");
		vi.spyOn(axios, "create").mockReturnValue(client);

		expect(await bootstrapAuth()).toEqual({ id: "u1", role: "admin" });
		expect(client.get).toHaveBeenNthCalledWith(1, AUTH_CONFIG_ENDPOINT);
		expect(client.get).toHaveBeenNthCalledWith(2, AUTH_ME_ENDPOINT);
		expect(client.interceptors.request.use).toHaveBeenCalledOnce();
		expect(client.interceptors.response.use).toHaveBeenCalledOnce();
	});

	it("refreshes jwt session before getting the current user", async () => {
		const client = createMockClient("jwt");
		vi.spyOn(axios, "create").mockReturnValue(client);

		expect(await bootstrapAuth()).toEqual({ id: "u1", role: "admin" });
		expect(client.post).toHaveBeenCalledWith("/auth/refresh", undefined, expect.any(Object));
		expect(client.get).toHaveBeenNthCalledWith(2, AUTH_ME_ENDPOINT);
	});

	it("bootstrapで生成したアダプタをfetchWithAuthと共有し、jwtのBearerを付与する", async () => {
		const client = createMockClient("jwt");
		vi.spyOn(axios, "create").mockReturnValue(client);
		await bootstrapAuth();

		const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: vi.fn() });
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		expect(fetchMock).toHaveBeenCalledOnce();
		const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(url).toBe("/api/projects");
		expect(new Headers(requestInit.headers).get("Authorization")).toBe("Bearer access-token");
	});

	it("bootstrap後のfetchWithAuthは/auth/configを再取得しない", async () => {
		const client = createMockClient("session");
		vi.spyOn(axios, "create").mockReturnValue(client);
		await bootstrapAuth();

		const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: vi.fn() });
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		expect(fetchMock).toHaveBeenCalledOnce();
		expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/projects");
	});
});
