/**
 * design doc: docs/basic_design/05_frontend.md §6 APIクライアント層（認証方式の吸収）
 * 設計書に明記された固定仕様値のため定数として定義する（config化は不要）。
 */

/** CSRFトークンを送るリクエストヘッダ名 */
export const CSRF_HEADER_NAME = "X-CSRF-Token";

/** frontendが利用するAPIの既定ベースURL */
export const DEFAULT_API_BASE_URL = "/api";

/** 起動時に認証方式を取得するAPIパス */
export const AUTH_CONFIG_ENDPOINT = "/auth/config";

/** 起動時に現在のユーザーを取得するAPIパス */
export const AUTH_ME_ENDPOINT = "/auth/me";

/** CSRF Cookie名の既定値。実際の値は将来 /auth/config から注入される想定（#178スコープ） */
export const DEFAULT_CSRF_COOKIE_NAME = "cerberus_csrf";

/** CSRFヘッダを付与する更新系HTTPメソッド（session §6の表より） */
export const MUTATING_HTTP_METHODS = ["post", "put", "patch", "delete"] as const;

/** jwtモードのリフレッシュAPIパス */
export const REFRESH_ENDPOINT_PATH = "/auth/refresh";

/** jwtモードのログアウトAPIパス（refresh同様にCookie+CSRFで送る） */
export const LOGOUT_ENDPOINT_PATH = "/auth/logout";

/** 401でもリトライ対象外とするパス（設計書§6.1「リフレッシュ対象外」） */
export const REFRESH_EXEMPT_PATHS = [
	"/auth/login",
	"/auth/refresh",
	"/auth/register",
	"/auth/oauth/exchange",
] as const;
