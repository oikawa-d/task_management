import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { fetchAuthMe, OAuthCallbackApiError, oauthExchange } from "./oauthCallbackApi";

describe("oauthExchange", () => {
	beforeEach(() => {
		setAuthAdapterMode("jwt");
	});

	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("正常時はaccess_tokenとredirect_toを含むレスポンスを返す", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () =>
				Promise.resolve({
					access_token: "token-123",
					token_type: "bearer",
					expires_in: 900,
					redirect_to: "/projects/1",
				}),
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await oauthExchange("handoff-code");

		expect(result.access_token).toBe("token-123");
		expect(result.redirect_to).toBe("/projects/1");
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/auth/oauth/exchange",
			expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "handoff-code" }) }),
		);
	});

	it("400 OAUTH_HANDOFF_INVALIDの場合はcode付きでOAuthCallbackApiErrorを投げる", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 400,
			json: () => Promise.resolve({ error: { code: "OAUTH_HANDOFF_INVALID" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const error = await oauthExchange("expired-code").catch((e: unknown) => e);

		expect(error).toBeInstanceOf(OAuthCallbackApiError);
		expect((error as OAuthCallbackApiError).status).toBe(400);
		expect((error as OAuthCallbackApiError).code).toBe("OAUTH_HANDOFF_INVALID");
	});

	it("403 USER_INACTIVEの場合はcode付きでOAuthCallbackApiErrorを投げる", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 403,
			json: () => Promise.resolve({ error: { code: "USER_INACTIVE" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const error = await oauthExchange("some-code").catch((e: unknown) => e);

		expect(error).toBeInstanceOf(OAuthCallbackApiError);
		expect((error as OAuthCallbackApiError).code).toBe("USER_INACTIVE");
	});

	it("エラーボディがJSONでない場合はcode未定義のOAuthCallbackApiErrorを投げる", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 503,
			json: () => Promise.reject(new Error("not json")),
		});
		vi.stubGlobal("fetch", fetchMock);

		const error = await oauthExchange("some-code").catch((e: unknown) => e);

		expect(error).toBeInstanceOf(OAuthCallbackApiError);
		expect((error as OAuthCallbackApiError).status).toBe(503);
		expect((error as OAuthCallbackApiError).code).toBeUndefined();
	});
});

describe("fetchAuthMe", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("正常時はprofile_completedを含むユーザー情報を返す", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: true }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await fetchAuthMe();

		expect(result).toEqual({ id: "user-1", role: "member", profile_completed: true });
		expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.objectContaining({ method: "GET" }));
	});

	it("401の場合はOAuthCallbackApiErrorを投げる", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 401,
			json: () => Promise.resolve({ error: { code: "UNAUTHENTICATED" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const error = await fetchAuthMe().catch((e: unknown) => e);

		expect(error).toBeInstanceOf(OAuthCallbackApiError);
		expect((error as OAuthCallbackApiError).status).toBe(401);
	});
});
