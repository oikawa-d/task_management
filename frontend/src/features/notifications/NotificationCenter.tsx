import { useEffect, useRef, useState } from "react";

import styles from "./NotificationCenter.module.css";
import { NotificationBell } from "./NotificationBell";
import { NotificationPanel } from "./NotificationPanel";
import type { NotificationItemData } from "./types";
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from "./hooks/useNotifications";

export interface NotificationCenterProps {
	unreadCount: number;
	notifications?: NotificationItemData[];
	page?: number;
	totalPages?: number;
	onPageChange?: (page: number) => void;
	onItemClick?: (notification: NotificationItemData) => void;
	onMarkAllRead?: () => void;
	enableDataApi?: boolean;
}

/**
 * ヘッダーの通知ベル＋通知パネルをまとめたコンテナ。
 * パネルの開閉状態のみをローカルstateで持ち、未読件数・通知一覧・既読化などの
 * データ取得・更新ロジックは一切持たない（すべてpropsで注入される）。
 */
export function NotificationCenter({
	unreadCount,
	notifications,
	page = 1,
	totalPages = 1,
	onPageChange,
	onItemClick,
	onMarkAllRead,
	enableDataApi = false,
}: NotificationCenterProps) {
	const [isOpen, setIsOpen] = useState(false);
	const [internalPage, setInternalPage] = useState(page);
	const bellRef = useRef<HTMLButtonElement>(null);
	const panelRef = useRef<HTMLDivElement>(null);
	const currentPage = onPageChange ? page : internalPage;
	const notificationQuery = useNotifications(currentPage, enableDataApi && isOpen && notifications === undefined);
	const markReadMutation = useMarkNotificationRead();
	const markAllMutation = useMarkAllNotificationsRead();

	const close = () => {
		setIsOpen(false);
		bellRef.current?.focus();
	};

	useEffect(() => {
		if (!isOpen) {
			return;
		}

		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") {
				close();
			}
		};

		const handlePointerDown = (event: MouseEvent) => {
			const target = event.target as Node;
			if (panelRef.current?.contains(target) || bellRef.current?.contains(target)) {
				return;
			}
			setIsOpen(false);
		};

		document.addEventListener("keydown", handleKeyDown);
		document.addEventListener("mousedown", handlePointerDown);
		return () => {
			document.removeEventListener("keydown", handleKeyDown);
			document.removeEventListener("mousedown", handlePointerDown);
		};
	}, [isOpen]);

	const handleItemClick = (notification: NotificationItemData) => {
		if (enableDataApi && notification.readAt === null) void markReadMutation.mutateAsync(notification.id);
		onItemClick?.(notification);
		close();
	};
	const handlePageChange = (nextPage: number) => {
		setInternalPage(nextPage);
		onPageChange?.(nextPage);
	};
	const handleMarkAllRead = () => {
		if (enableDataApi) void markAllMutation.mutateAsync();
		onMarkAllRead?.();
	};
	const displayNotifications = notifications ?? notificationQuery.data?.items ?? [];
	const displayTotalPages = notifications ? totalPages : notificationQuery.data?.totalPages ?? 1;

	return (
		<div className={styles.wrapper}>
			<NotificationBell
				ref={bellRef}
				unreadCount={unreadCount}
				isOpen={isOpen}
				onClick={() => setIsOpen((current) => !current)}
			/>
			{isOpen && (
				<NotificationPanel
					ref={panelRef}
					notifications={displayNotifications}
					unreadCount={unreadCount}
					page={currentPage}
					totalPages={displayTotalPages}
					onPageChange={handlePageChange}
					onItemClick={handleItemClick}
					onMarkAllRead={handleMarkAllRead}
					isLoading={enableDataApi && notificationQuery.isLoading}
					errorMessage={enableDataApi && notificationQuery.isError ? "通知を読み込めませんでした。" : null}
					onRetry={() => void notificationQuery.refetch()}
				/>
			)}
		</div>
	);
}
