import type { AxiosError, AxiosRequestConfig } from "axios";

/** design doc: docs/basic_design/05_frontend.md §6 APIクライアント層（認証方式の吸収） */
export type AuthMode = "session" | "jwt";

/** リトライ管理用フラグを追加したリクエスト設定（§6.1「リトライ回数は1回のみ」） */
export interface RetryableRequestConfig extends AxiosRequestConfig {
	_retried?: boolean;
}

/** ログイン成功レスポンスのうち認証アダプタが必要とする最小限のフィールド */
export interface LoginSuccessResponse {
	access_token?: string;
}

/** 認証方式（session / jwt）の差異を吸収するアダプタのインターフェース */
export interface AuthAdapter {
	readonly mode: AuthMode;
	/** リクエスト直前の認証情報付与（Cookie送信設定 / CSRFヘッダ / Bearerヘッダ） */
	attach(config: RetryableRequestConfig): RetryableRequestConfig;
	/** ログインレスポンスから必要な情報を保持する */
	onLoginSuccess(response: LoginSuccessResponse): void;
	/** 401時の復帰処理。trueを返した場合のみ元リクエストを再送する */
	onUnauthorized(error: AxiosError): Promise<boolean>;
	/** アプリ起動時に既存の認証状態を復元する */
	restoreSession(): Promise<boolean>;
	/** クライアント側の後片付け */
	onLogout(): void;
	/** logout APIを呼び出す。認証方式固有のCookie/CSRF設定は実装側で付与する */
	logout(): Promise<void>;
}

/**
 * jwtモードのアクセストークン保持先を注入するためのインターフェース。
 * 将来 authStore（Zustand）実装後は、これを満たすアダプタを渡すことで接続できる。
 */
export interface TokenStore {
	getAccessToken(): string | null;
	setAccessToken(token: string | null): void;
}
