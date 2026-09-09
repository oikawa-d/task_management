import { useEffect, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { NotificationCenter } from "../features/notifications";
import { useUnreadCount } from "../features/notifications/hooks/useUnreadCount";
import type { NotificationItemData } from "../features/notifications/types";
import { ROUTES } from "../routes";

export interface AppLayoutProps {
	notifications?: NotificationItemData[];
	notificationPage?: number;
	notificationTotalPages?: number;
	onNotificationPageChange?: (page: number) => void;
	onNotificationItemClick?: (notification: NotificationItemData) => void;
	onMarkAllNotificationsRead?: () => void;
}

export function AppLayout({
	notifications = [],
	notificationPage = 1,
	notificationTotalPages = 1,
	onNotificationPageChange,
	onNotificationItemClick,
	onMarkAllNotificationsRead,
}: AppLayoutProps = {}) {
	const user = useAuthStore((state) => state.user);
	const status = useAuthStore((state) => state.status);
	const authAdapter = useAuthStore((state) => state.authAdapter);
	const clearAuth = useAuthStore((state) => state.clear);
	const navigate = useNavigate();
	const [isLoggingOut, setIsLoggingOut] = useState(false);
	const [unreadOverride, setUnreadOverride] = useState<number | null>(null);
	const [currentNotificationPage, setCurrentNotificationPage] = useState(notificationPage);
	const { data: polledUnreadCount } = useUnreadCount({ isAuthenticated: status === "authenticated" });
	const isAdmin = user?.role === "admin";
	const unreadCount = unreadOverride ?? polledUnreadCount ?? 0;
	const handleNotificationPageChange = onNotificationPageChange ?? setCurrentNotificationPage;

	useEffect(() => {
		if (polledUnreadCount !== undefined) {
			setUnreadOverride(null);
		}
	}, [polledUnreadCount]);

	const handleLogout = async () => {
		if (isLoggingOut) {
			return;
		}

		setIsLoggingOut(true);
		try {
			await authAdapter?.logout();
		} catch {
			// API失敗時もクライアント側の認証状態を破棄する
		} finally {
			clearAuth();
			navigate(ROUTES.LOGIN, { replace: true });
		}
	};

	const handleNotificationClick = (notification: NotificationItemData) => {
		onNotificationItemClick?.(notification);
		if (!onNotificationItemClick && notification.task) {
			navigate(ROUTES.PROJECT(notification.task.projectId));
		}
	};

	return (
		<div>
			<header>
				<span>Cerberus</span>
				<NotificationCenter
					unreadCount={unreadCount}
					notifications={notifications}
					page={currentNotificationPage}
					totalPages={notificationTotalPages}
					onPageChange={handleNotificationPageChange}
					onItemClick={handleNotificationClick}
					onMarkAllRead={onMarkAllNotificationsRead ?? (() => setUnreadOverride(0))}
				/>
			</header>
			<nav aria-label="サイドバー">
				<Link to={ROUTES.DASHBOARD}>home</Link>
				<Link to={ROUTES.SETTINGS}>設定</Link>
				{isAdmin ? <Link to={ROUTES.ADMIN_USERS}>管理</Link> : null}
				<button type="button" onClick={handleLogout} disabled={isLoggingOut}>
					ログアウト
				</button>
			</nav>
			<main>
				<Outlet />
			</main>
		</div>
	);
}
