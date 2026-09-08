import { JwtAdapter } from "./jwtAdapter";
import { SessionAdapter } from "./sessionAdapter";
import type { AuthAdapter, AuthMode } from "./types";

export { JwtAdapter } from "./jwtAdapter";
export { SessionAdapter } from "./sessionAdapter";
export type { AuthAdapter, AuthMode, LoginSuccessResponse, RetryableRequestConfig, TokenStore } from "./types";

/**
 * auth_mode（"session" | "jwt"）に応じたAuthAdapterを生成するファクトリ。
 * auth_modeの取得元（/auth/config）はこの層のスコープ外で、値を引数として受け取るのみとする。
 */
export function createAuthAdapter(mode: AuthMode): AuthAdapter {
	switch (mode) {
		case "session":
			return new SessionAdapter();
		case "jwt":
			return new JwtAdapter();
		default: {
			const exhaustiveCheck: never = mode;
			throw new Error(`Unknown auth mode: ${String(exhaustiveCheck)}`);
		}
	}
}
