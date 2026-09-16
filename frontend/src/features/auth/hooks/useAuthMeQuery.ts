import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { fetchAuthMe, type AuthMeResult } from "../api/oauthCallbackApi";

export const AUTH_ME_QUERY_KEY = ["auth", "me"] as const;

/**
 * design doc: docs/detailed_design/screen/11_oauth_callback.md §4, §8 useAuthMeQuery
 *
 * `GET /auth/me` によるログイン確立確認。`refetch` はキャッシュを介さず必ず最新値を取得し、
 * 失敗時は例外をそのままthrowする（呼び出し側の`runCallback`でcatchして③表示へ分岐する）。
 */
export function useAuthMeQuery(): { refetch: (signal?: AbortSignal) => Promise<AuthMeResult> } {
	const queryClient = useQueryClient();

	const refetch = useCallback(
		(signal?: AbortSignal) =>
			queryClient.fetchQuery({
				queryKey: AUTH_ME_QUERY_KEY,
				queryFn: () => fetchAuthMe(signal),
				staleTime: 0,
			}),
		[queryClient],
	);

	return { refetch };
}
