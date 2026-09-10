import { setAuthAdapter } from "../api/authAdapter/client";
import {
	AUTH_CONFIG_ENDPOINT,
	AUTH_ME_ENDPOINT,
} from "../api/authAdapter/constants";
import { createAuthAdapter } from "../api/authAdapter";
import { configureApiClient, getApiClient } from "../api/client";
import type { AuthUser } from "./authStore";
import { useAuthStore } from "./authStore";

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
	const client = getApiClient();
	const { data: config } = await client.get<AuthConfigResponse>(AUTH_CONFIG_ENDPOINT);
	const adapter = createAuthAdapter(config.auth_mode, {
		csrfCookieName: config.csrf_cookie_name,
		httpClient: client,
	});
	useAuthStore.getState().setAuthAdapter(adapter);
	setAuthAdapter(adapter);

	configureApiClient(client, {
		authAdapter: adapter,
		onLogout: () => useAuthStore.getState().setUnauthenticated(),
	});
	if (!(await adapter.restoreSession())) {
		return null;
	}

	const { data: user } = await client.get<AuthMeResponse>(AUTH_ME_ENDPOINT);
	return { id: user.id, role: user.role };
}
