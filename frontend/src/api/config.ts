/** axiosクライアントのリクエストタイムアウト（ミリ秒）。バックエンドの応答遅延を考慮した既定値。 */
const DEFAULT_TIMEOUT_MS = 10000;

export interface ApiClientConfig {
	baseURL: string;
	timeoutMs: number;
}

/**
 * axiosインスタンス生成に必要な設定値を環境変数から読み取る。
 * `VITE_API_BASE_URL` は `.env.example` で定義済みの必須値のため、未設定時は起動時エラーとして扱う。
 */
export function getApiClientConfig(): ApiClientConfig {
	const baseURL = import.meta.env.VITE_API_BASE_URL;

	if (!baseURL) {
		throw new Error("VITE_API_BASE_URL が設定されていません");
	}

	return {
		baseURL,
		timeoutMs: DEFAULT_TIMEOUT_MS,
	};
}
