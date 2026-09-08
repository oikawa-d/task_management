import { JwtAdapter } from "./jwtAdapter";
import { SessionAdapter } from "./sessionAdapter";
import type { AuthAdapter, AuthAdapterOptions, AuthMode } from "./types";

export { JwtAdapter } from "./jwtAdapter";
export { SessionAdapter } from "./sessionAdapter";
export type { AuthAdapter, AuthAdapterOptions, AuthMode, LoginSuccessResponse, RetryableRequestConfig, TokenStore } from "./types";

/**
 * auth_mode（"session" | "jwt"）に応じたAuthAdapterを生成するファクトリ。
 * auth_modeの取得元（/auth/config）はこの層のスコープ外で、値を引数として受け取るのみとする。
 */
export function createAuthAdapter(mode: AuthMode, options: AuthAdapterOptions = {}): AuthAdapter {
	switch (mode) {
		case "session":
			return new SessionAdapter(options.csrfCookieName);
		case "jwt":
			return new JwtAdapter(options.tokenStore, options.httpClient, options.csrfCookieName);
		default: {
			const exhaustiveCheck: never = mode;
			throw new Error(`Unknown auth mode: ${String(exhaustiveCheck)}`);
		}
	}
}
