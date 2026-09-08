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
		// 401（UNAUTHENTICATED/SESSION_EXPIRED）はリトライしても回復しないため即座に諦める。
		// 詳細設計 docs/detailed_design/api/notifications/02_get_notifications_unread_count.md §3 は
		// SESSION_EXPIRED時のポーリング停止（enabled: false化）を規定しているが、
		// それには authStore との結線が必要で別task（#179/#178）のスコープのため、
		// 本taskでは最低限のリトライ抑止のみ行う。
		retry: (failureCount, error) => {
			if (error instanceof UnreadCountFetchError && error.status === 401) {
				return false;
			}
			return failureCount < 3;
		},
	});
}
