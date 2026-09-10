import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { AuthApiError, requestPasswordReset, resendVerification, resetPassword } from "./authApi";

function response(body: unknown, init: { ok: boolean; status: number; headers?: Record<string, string> }) {
	return {
		ok: init.ok,
		status: init.status,
		headers: new Headers(init.headers),
		json: vi.fn().mockResolvedValue(body),
	};
}

describe("authApi", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("requestPasswordResetは202を正常終了として扱う", async () => {
		const fetchMock = vi.fn().mockResolvedValue(
			response({ message: "送信しました" }, { ok: true, status: 202 }),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(requestPasswordReset("user@example.com")).resolves.toBeUndefined();
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/auth/password/forgot",
			expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "user@example.com" }) }),
		);
	});

	it("requestPasswordResetの422はAuthApiErrorとしてdetailsを保持する", async () => {
		const details = [{ field: "email", message: "メールアドレスの形式が正しくありません" }];
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			response({ error: { code: "VALIDATION_ERROR", message: "入力内容に誤りがあります", details } }, { ok: false, status: 422 }),
		));

		const error = await requestPasswordReset("bad").catch((e: unknown) => e);
		expect(error).toBeInstanceOf(AuthApiError);
		expect((error as AuthApiError).code).toBe("VALIDATION_ERROR");
		expect((error as AuthApiError).details).toEqual(details);
	});

	it("429はRetry-Afterを秒数として保持する", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			response(
				{ error: { code: "TOO_MANY_ATTEMPTS", message: "しばらくお待ちください" } },
				{ ok: false, status: 429, headers: { "Retry-After": "120" } },
			),
		));

		const error = await requestPasswordReset("user@example.com").catch((e: unknown) => e);
		expect(error).toBeInstanceOf(AuthApiError);
		expect((error as AuthApiError).retryAfterSeconds).toBe(120);
	});

	it("resetPasswordは204を正常終了として扱う", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response(undefined, { ok: true, status: 204 }));
		vi.stubGlobal("fetch", fetchMock);

		await expect(resetPassword({ token: "tok", new_password: "Newpass1", password_confirm: "Newpass1" })).resolves.toBeUndefined();
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/auth/password/reset",
			expect.objectContaining({ method: "POST" }),
		);
	});

	it("resetPasswordの400 INVALID_RESET_TOKENをAuthApiErrorとして返す", async () => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
			response({ error: { code: "INVALID_RESET_TOKEN", message: "リセットリンクが無効か、有効期限が切れています" } }, { ok: false, status: 400 }),
		));

		const error = await resetPassword({ token: "tok", new_password: "Newpass1", password_confirm: "Newpass1" }).catch((e: unknown) => e);
		expect(error).toEqual(expect.objectContaining({ status: 400, code: "INVALID_RESET_TOKEN" }));
	});

	it("resendVerificationは202を正常終了として扱う", async () => {
		const fetchMock = vi.fn().mockResolvedValue(response({ message: "送信しました" }, { ok: true, status: 202 }));
		vi.stubGlobal("fetch", fetchMock);

		await expect(resendVerification("user@example.com")).resolves.toBeUndefined();
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/auth/verify-email/resend",
			expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "user@example.com" }) }),
		);
	});

	it("ネットワークエラー時はAuthApiError(NETWORK_ERROR)を投げる", async () => {
		vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

		const error = await requestPasswordReset("user@example.com").catch((e: unknown) => e);
		expect(error).toEqual(expect.objectContaining({ status: 0, code: "NETWORK_ERROR" }));
	});
});
