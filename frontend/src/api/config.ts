import { DEFAULT_API_BASE_URL } from "./authAdapter/constants";

const DEFAULT_TIMEOUT_MS = 10000;

export interface ApiClientConfig {
	baseURL: string;
	timeoutMs: number;
}

/** Viteの公開設定から、共通Axiosクライアントの接続設定を構築する。 */
export function getApiClientConfig(): ApiClientConfig {
	return {
		baseURL: import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
		timeoutMs: DEFAULT_TIMEOUT_MS,
	};
}
