import axios, { type AxiosInstance } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTH_CONFIG_ENDPOINT, AUTH_ME_ENDPOINT } from "../api/authAdapter/constants";
import { bootstrapAuth } from "./authBootstrap";

function createMockClient(authMode: "session" | "jwt"): AxiosInstance {
	return {
		get: vi
			.fn()
			.mockResolvedValueOnce({
				data: { auth_mode: authMode, google_login_enabled: false, csrf_cookie_name: "csrf" },
			})
			.mockResolvedValueOnce({ data: { id: "u1", role: "admin", profile_completed: true } }),
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
	});

	it("gets config, restores the session, then gets the current user", async () => {
		const client = createMockClient("session");
		vi.spyOn(axios, "create").mockReturnValue(client);

		expect(await bootstrapAuth()).toEqual({ id: "u1", role: "admin", profileCompleted: true });
		expect(client.get).toHaveBeenNthCalledWith(1, AUTH_CONFIG_ENDPOINT);
		expect(client.get).toHaveBeenNthCalledWith(2, AUTH_ME_ENDPOINT);
		expect(client.interceptors.request.use).toHaveBeenCalledOnce();
		expect(client.interceptors.response.use).toHaveBeenCalledOnce();
	});

	it("refreshes jwt session before getting the current user", async () => {
		const client = createMockClient("jwt");
		vi.spyOn(axios, "create").mockReturnValue(client);

		expect(await bootstrapAuth()).toEqual({ id: "u1", role: "admin", profileCompleted: true });
		expect(client.post).toHaveBeenCalledWith("/auth/refresh", undefined, expect.any(Object));
		expect(client.get).toHaveBeenNthCalledWith(2, AUTH_ME_ENDPOINT);
	});
});
