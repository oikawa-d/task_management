import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getNotifications, markAllNotificationsRead, markNotificationRead } from "../api/notificationsApi";
import { UNREAD_COUNT_QUERY_KEY } from "./useUnreadCount";

export const NOTIFICATIONS_QUERY_KEY = ["notifications"] as const;

export function useNotifications(page: number, enabled: boolean) {
	return useQuery({
		queryKey: [...NOTIFICATIONS_QUERY_KEY, page],
		queryFn: () => getNotifications(page),
		enabled,
	});
}

export function useMarkNotificationRead() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: markNotificationRead,
		onSuccess: ({ unreadCount }) => {
			queryClient.setQueryData(UNREAD_COUNT_QUERY_KEY, unreadCount);
			void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
		},
	});
}

export function useMarkAllNotificationsRead() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: markAllNotificationsRead,
		onSuccess: ({ unreadCount }) => {
			queryClient.setQueryData(UNREAD_COUNT_QUERY_KEY, unreadCount);
			void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
		},
	});
}
