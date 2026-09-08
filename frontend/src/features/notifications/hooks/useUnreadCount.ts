import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchUnreadCount } from "../api/unreadCountApi";
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
		queryFn: async () => {
			const response = await fetchUnreadCount();
			return response.unread_count;
		},
		enabled: isAuthenticated,
		refetchInterval: getNotificationPollIntervalMs(),
		refetchIntervalInBackground: false,
	});
}
