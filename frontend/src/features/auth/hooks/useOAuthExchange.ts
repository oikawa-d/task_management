import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { setAuthAccessToken } from "../../../api/authAdapter/client";
import { oauthExchange, type OAuthExchangeResult } from "../api/oauthCallbackApi";

/**
 * design doc: docs/detailed_design/screen/11_oauth_callback.md §9.1 useOAuthExchange
 *
 * jwtモードのハンドオフコード交換。成功時はaccessTokenを共通APIクライアント
 * （api/authAdapter/client）のTokenStoreへ保存し、以降のfetchWithAuth呼び出しへ引き継ぐ。
 */
export function useOAuthExchange(): UseMutationResult<OAuthExchangeResult, unknown, { code: string }> {
	return useMutation({
		mutationKey: ["auth", "oauthExchange"],
		mutationFn: ({ code }: { code: string }) => oauthExchange(code),
		onSuccess: (result) => {
			setAuthAccessToken(result.access_token);
		},
	});
}
