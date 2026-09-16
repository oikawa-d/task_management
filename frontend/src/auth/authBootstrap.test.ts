import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, fetchWithAuth } from "../api/authAdapter/client";
import { AUTH_CONFIG_ENDPOINT, AUTH_ME_ENDPOINT } from "../api/authAdapter/constants";
import { queryClient } from "../lib/queryClient";
import { useProjectStore } from "../stores/projectStore";
import { bootstrapAuth } from "./authBootstrap";
import { useAuthStore } from "./authStore";

function stubBootstrapFetch(authMode: "session" | "jwt") {
	const fetchMock = vi.fn()
		.mockResolvedValueOnce({
			ok: true,
			status: 200,
			json: vi.fn().mockResolvedValue({ auth_mode: authMode, google_login_enabled: false, csrf_cookie_name: "csrf" }),
		})
		.mockResolvedValueOnce({ ok: true, status: 200, json: vi.fn().mockResolvedValue({ id: "u1", role: "admin" }) });
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

describe("bootstrapAuth", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		clearAuthAdapter();
		queryClient.clear();
		useProjectStore.getState().clearSelectedProject();
		useAuthStore.getState().reset();
	});

	it("gets config, restores the session, then gets the current user", async () => {
		vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: "access-token" } } as never);
		const fetchMock = stubBootstrapFetch("session");

		expect(await bootstrapAuth()).toEqual({ id: "u1", role: "admin" });
		expect(fetchMock).toHaveBeenNthCalledWith(1, `/api${AUTH_CONFIG_ENDPOINT}`, expect.any(Object));
		expect(fetchMock).toHaveBeenNthCalledWith(2, `/api${AUTH_ME_ENDPOINT}`, expect.any(Object));
	});

	it("refreshes jwt session before getting the current user", async () => {
		const postMock = vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: "access-token" } } as never);
		const fetchMock = stubBootstrapFetch("jwt");

		expect(await bootstrapAuth()).toEqual({ id: "u1", role: "admin" });
		expect(postMock).toHaveBeenCalledWith("/auth/refresh", undefined, expect.any(Object));
		expect(fetchMock).toHaveBeenNthCalledWith(2, `/api${AUTH_ME_ENDPOINT}`, expect.any(Object));
	});

	it("bootstrapで生成したアダプタをfetchWithAuthと共有し、jwtのBearerを付与する", async () => {
		vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: "access-token" } } as never);
		stubBootstrapFetch("jwt");
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
		vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: "access-token" } } as never);
		stubBootstrapFetch("session");
		await bootstrapAuth();

		const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: vi.fn() });
		vi.stubGlobal("fetch", fetchMock);

		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");

		expect(fetchMock).toHaveBeenCalledOnce();
		expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/projects");
	});

	it("401で自動ログアウトするとユーザー別キャッシュと選択stateを破棄する", async () => {
		vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: "access-token" } } as never);
		const bootstrapFetch = stubBootstrapFetch("session");
		useProjectStore.getState().selectProject("project-1");
		queryClient.setQueryData(["projects", { page: 1 }], { items: [{ id: "project-1" }] });

		await bootstrapAuth();
		bootstrapFetch.mockResolvedValue({ ok: false, status: 401, json: vi.fn().mockResolvedValue({ error: { code: "UNAUTHENTICATED" } }) });
		await fetchWithAuth("/api/projects", { method: "GET" }, "/api");
		expect(useAuthStore.getState().status).toBe("unauthenticated");
		expect(useProjectStore.getState().selectedProjectId).toBeNull();
		expect(queryClient.getQueryData(["projects", { page: 1 }])).toBeUndefined();
	});
});
