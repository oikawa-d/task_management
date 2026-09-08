import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchUnreadCount, UnreadCountFetchError } from "../api/unreadCountApi";
import { getNotificationPollIntervalMs } from "../config/pollingConfig";

export const UNREAD_COUNT_QUERY_KEY = ["notifications", "unread-count"] as const;

export interface UseUnreadCountOptions {
	/**
	 * 認証済みかどうか。未認証時はポーリング自体を止める
	 * （docs/basic_design/05_frontend.md §3.1「停止条件」）。
	 * authStore（#179で実装予定）が無いため、呼び出し側から注入する。
	 */
	isAuthenticated: boolean;
}

/**
 * 未読通知件数を定期ポーリングで取得するstate管理hook。
 * ポーリング間隔は `VITE_NOTIFICATION_POLL_INTERVAL_MS` から取得し（既定60000ms）、
 * 未認証時・タブが非アクティブな間はポーリングを行わない。
 */
export function useUnreadCount({
	isAuthenticated,
}: UseUnreadCountOptions): UseQueryResult<number> {
	return useQuery({
		queryKey: UNREAD_COUNT_QUERY_KEY,
		queryFn: async ({ signal }) => {
			const response = await fetchUnreadCount(signal);
			return response.unread_count;
		},
		enabled: isAuthenticated,
		refetchInterval: getNotificationPollIntervalMs(),
		refetchIntervalInBackground: false,
		// 401はリトライしても回復しないため即座に諦める（リトライストーム防止）。
		// 詳細設計 docs/detailed_design/api/notifications/02_get_notifications_unread_count.md §3 では
		// 401配下に UNAUTHENTICATED / SESSION_EXPIRED / TOKEN_EXPIRED の3種があり、
		// 本来は SESSION_EXPIRED でポーリング停止（enabled: false化）、
		// TOKEN_EXPIRED（jwtモード）でリフレッシュ後の再試行、という分岐が必要だが、
		// いずれも authStore / 共通APIクライアントとの結線が前提となり別task（#178/#179）のスコープ。
		// 本taskではエラーコード別の分岐は行わず、HTTPステータスのみで一律リトライ抑止する。
		// #178/#179 のマージ後にエラーコード別の制御へ差し替えること。
		retry: (failureCount, error) => {
			if (error instanceof UnreadCountFetchError && error.status === 401) {
				return false;
			}
			return failureCount < 3;
		},
	});
}
