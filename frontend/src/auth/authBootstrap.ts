import { setAuthAdapter } from "../api/authAdapter/client";
import {
	AUTH_CONFIG_ENDPOINT,
	AUTH_ME_ENDPOINT,
} from "../api/authAdapter/constants";
import { createAuthAdapter } from "../api/authAdapter";
import { fetchWithAuth } from "../api/authAdapter/client";
import { clearUserSessionState } from "./sessionCleanup";
import type { AuthUser } from "./authStore";
import { useAuthStore } from "./authStore";
import { authTokenStore } from "./tokenStore";

export type AuthConfigResponse = {
	auth_mode: "session" | "jwt";
	google_login_enabled: boolean;
	csrf_cookie_name: string;
};

type AuthMeResponse = {
	id: string;
	role: AuthUser["role"];
};

export async function bootstrapAuth(): Promise<AuthUser | null> {
	const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "/api";
	const configResponse = await fetch(`${apiBaseUrl}${AUTH_CONFIG_ENDPOINT}`, {
		method: "GET",
		credentials: "same-origin",
		headers: { Accept: "application/json" },
	});
	if (!configResponse.ok) {
		throw new Error(`auth config request failed: ${configResponse.status}`);
	}
	const config = (await configResponse.json()) as AuthConfigResponse;
	const adapter = createAuthAdapter(config.auth_mode, {
		csrfCookieName: config.csrf_cookie_name,
		tokenStore: authTokenStore,
	});
	const handleLogout = () => {
		clearUserSessionState();
		useAuthStore.getState().setUnauthenticated();
	};
	useAuthStore.getState().setAuthAdapter(adapter);
	useAuthStore.getState().setGoogleLoginEnabled(config.google_login_enabled);
	setAuthAdapter(adapter, handleLogout);

	if (!(await adapter.restoreSession())) {
		return null;
	}

	const userResponse = await fetchWithAuth(`${apiBaseUrl}${AUTH_ME_ENDPOINT}`, {
		method: "GET",
		headers: { Accept: "application/json" },
	}, apiBaseUrl);
	if (!userResponse.ok) {
		throw new Error(`auth me request failed: ${userResponse.status}`);
	}
	const user = (await userResponse.json()) as AuthMeResponse;
	return { id: user.id, role: user.role };
}
