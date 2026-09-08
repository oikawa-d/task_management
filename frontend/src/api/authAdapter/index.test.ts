import { describe, expect, it } from "vitest";

import { createAuthAdapter } from "./index";
import { JwtAdapter } from "./jwtAdapter";
import { SessionAdapter } from "./sessionAdapter";

describe("createAuthAdapter", () => {
	it("'session'を渡すとSessionAdapterを返す", () => {
		const adapter = createAuthAdapter("session");

		expect(adapter).toBeInstanceOf(SessionAdapter);
		expect(adapter.mode).toBe("session");
	});

	it("'jwt'を渡すとJwtAdapterを返す", () => {
		const adapter = createAuthAdapter("jwt");

		expect(adapter).toBeInstanceOf(JwtAdapter);
		expect(adapter.mode).toBe("jwt");
	});
});
