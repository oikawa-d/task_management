import { afterEach, describe, expect, it } from "vitest";

import { authTokenStore, useAuthStore } from "./authStore";

describe("authStore", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("stores and exposes the JWT access token through TokenStore", () => {
		authTokenStore.setAccessToken("access-token");

		expect(authTokenStore.getAccessToken()).toBe("access-token");
	});

	it("clears the token when authentication is lost", () => {
		authTokenStore.setAccessToken("access-token");

		useAuthStore.getState().setUnauthenticated();

		expect(authTokenStore.getAccessToken()).toBeNull();
	});
});
