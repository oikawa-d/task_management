import type { AxiosInstance } from "axios";

import {
	AUTH_CONFIG_ENDPOINT,
	AUTH_ME_ENDPOINT,
	DEFAULT_API_BASE_URL,
} from "../api/authAdapter/constants";
import { createAuthAdapter } from "../api/authAdapter";
import { configureApiClient, createApiClient, getApiClient } from "../api/client";
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

function getApiBaseUrl(): string {
	return import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
}

export function createAuthClient(baseURL = getApiBaseUrl()): AxiosInstance {
	return createApiClient({ baseURL });
}

export async function bootstrapAuth(): Promise<AuthUser | null> {
	const client = getApiClient();
	const { data: config } = await client.get<AuthConfigResponse>(AUTH_CONFIG_ENDPOINT);
	const adapter = createAuthAdapter(config.auth_mode, {
		csrfCookieName: config.csrf_cookie_name,
		httpClient: client,
	});
	useAuthStore.getState().setAuthAdapter(adapter);

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
