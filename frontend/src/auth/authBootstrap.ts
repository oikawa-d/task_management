import axios, { type AxiosInstance } from "axios";

import {
	AUTH_CONFIG_ENDPOINT,
	AUTH_ME_ENDPOINT,
	DEFAULT_API_BASE_URL,
} from "../api/authAdapter/constants";
import { createAuthAdapter, type RetryableRequestConfig } from "../api/authAdapter";
import type { AuthUser } from "./authStore";

export type AuthConfigResponse = {
	auth_mode: "session" | "jwt";
	google_login_enabled: boolean;
	csrf_cookie_name: string;
};

type AuthMeResponse = {
	id: string;
	role: AuthUser["role"];
	profile_completed: boolean;
};

function getApiBaseUrl(): string {
	return import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
}

export function createAuthClient(baseURL = getApiBaseUrl()): AxiosInstance {
	return axios.create({ baseURL });
}

function installAuthInterceptors(client: AxiosInstance, adapter: ReturnType<typeof createAuthAdapter>): void {
	client.interceptors.request.use((config) => adapter.attach(config as RetryableRequestConfig) as typeof config);
	client.interceptors.response.use(undefined, async (error: unknown) => {
		if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) {
			throw error;
		}

		const shouldRetry = await adapter.onUnauthorized(error);
		if (!shouldRetry) {
			throw error;
		}

		return client.request(error.config as RetryableRequestConfig);
	});
}

export async function bootstrapAuth(): Promise<AuthUser | null> {
	const client = createAuthClient();
	const { data: config } = await client.get<AuthConfigResponse>(AUTH_CONFIG_ENDPOINT);
	const adapter = createAuthAdapter(config.auth_mode, {
		csrfCookieName: config.csrf_cookie_name,
		httpClient: client,
	});

	installAuthInterceptors(client, adapter);
	if (!(await adapter.restoreSession())) {
		return null;
	}

	const { data: user } = await client.get<AuthMeResponse>(AUTH_ME_ENDPOINT);
	return {
		id: user.id,
		role: user.role,
		profileCompleted: user.profile_completed,
	};
}
