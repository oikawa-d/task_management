import type { AxiosInstance } from "axios";
import { describe, expect, it, vi } from "vitest";

import { createAuthAdapter } from "./index";
import { JwtAdapter } from "./jwtAdapter";
import { SessionAdapter } from "./sessionAdapter";

describe("createAuthAdapter", () => {
	it("'session'を渡すとSessionAdapterを返す", () => {
		const adapter = createAuthAdapter("session");

		expect(adapter).toBeInstanceOf(SessionAdapter);
		expect(adapter.mode).toBe("session");
	});

	it("session adapterへ注入したAPI clientを引き継ぐ", async () => {
		const httpClient = { post: vi.fn(async () => undefined) } as unknown as AxiosInstance;
		const adapter = createAuthAdapter("session", { httpClient });

		await adapter.logout();

		expect(httpClient.post).toHaveBeenCalledWith("/auth/logout", undefined, expect.any(Object));
	});

	it("'jwt'を渡すとJwtAdapterを返す", () => {
		const adapter = createAuthAdapter("jwt");

		expect(adapter).toBeInstanceOf(JwtAdapter);
		expect(adapter.mode).toBe("jwt");
	});
});
