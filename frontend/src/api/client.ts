import axios, { type AxiosInstance } from "axios";

import { getApiClientConfig } from "./config";
import { toApiError } from "./errors";

/**
 * 共通のaxiosインスタンスを生成する。
 *
 * 認証方式（session / jwt）の差異吸収は #179（認証方式差異吸収アダプタ実装）で
 * `interceptors.request` へ追加される想定のため、本関数はエラーハンドリングのみを担う。
 */
export function createApiClient(): AxiosInstance {
	const { baseURL, timeoutMs } = getApiClientConfig();

	const client = axios.create({
		baseURL,
		timeout: timeoutMs,
		headers: {
			"Content-Type": "application/json",
		},
	});

	client.interceptors.response.use(
		(response) => response,
		(error: unknown) => Promise.reject(toApiError(error)),
	);

	return client;
}

let sharedClient: AxiosInstance | undefined;

/**
 * アプリ全体で共有するAPIクライアントを取得する。
 * 初回呼び出し時にのみ {@link createApiClient} でインスタンスを生成し、以降は使い回す。
 * モジュール読み込み時ではなく呼び出し時に生成することで、環境変数未設定時のエラーを
 * 実際にAPIクライアントを利用する箇所まで遅延させる。
 */
export function getApiClient(): AxiosInstance {
	if (!sharedClient) {
		sharedClient = createApiClient();
	}
	return sharedClient;
}
