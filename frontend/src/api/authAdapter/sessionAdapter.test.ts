import type { AxiosError } from "axios";
import { beforeEach, describe, expect, it } from "vitest";

import { CSRF_HEADER_NAME } from "./constants";
import { SessionAdapter } from "./sessionAdapter";

function clearCookies(): void {
	document.cookie.split(";").forEach((cookie) => {
		const name = cookie.split("=")[0]?.trim();
		if (name) {
			document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
		}
	});
}

describe("SessionAdapter", () => {
	beforeEach(() => {
		clearCookies();
	});

	it("常にwithCredentialsを付与する", () => {
		const adapter = new SessionAdapter();

		const attached = adapter.attach({ method: "get", url: "/projects" });

		expect(attached.withCredentials).toBe(true);
	});

	it("更新系メソッドではCookieのCSRFトークンをヘッダへ付与する", () => {
		document.cookie = "cerberus_csrf=csrf-value";
		const adapter = new SessionAdapter();

		const attached = adapter.attach({ method: "patch", url: "/tasks/1" });

		expect(attached.headers?.[CSRF_HEADER_NAME]).toBe("csrf-value");
	});

	it("GETメソッドではCSRFヘッダを付与しない", () => {
		document.cookie = "cerberus_csrf=csrf-value";
		const adapter = new SessionAdapter();

		const attached = adapter.attach({ method: "get", url: "/projects" });

		expect(attached.headers?.[CSRF_HEADER_NAME]).toBeUndefined();
	});

	it("onUnauthorizedは常にfalseを返す（リトライしない）", async () => {
		const adapter = new SessionAdapter();

		const result = await adapter.onUnauthorized({} as AxiosError);

		expect(result).toBe(false);
	});
});
