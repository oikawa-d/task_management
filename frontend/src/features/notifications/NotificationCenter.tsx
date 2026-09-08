import { useEffect, useRef, useState } from "react";

import styles from "./NotificationCenter.module.css";
import { NotificationBell } from "./NotificationBell";
import { NotificationPanel } from "./NotificationPanel";
import type { NotificationItemData } from "./types";

export interface NotificationCenterProps {
	unreadCount: number;
	notifications: NotificationItemData[];
	page: number;
	totalPages: number;
	onPageChange: (page: number) => void;
	onItemClick: (notification: NotificationItemData) => void;
	onMarkAllRead: () => void;
}

/**
 * ヘッダーの通知ベル＋通知パネルをまとめたコンテナ。
 * パネルの開閉状態のみをローカルstateで持ち、未読件数・通知一覧・既読化などの
 * データ取得・更新ロジックは一切持たない（すべてpropsで注入される）。
 */
export function NotificationCenter({
	unreadCount,
	notifications,
	page,
	totalPages,
	onPageChange,
	onItemClick,
	onMarkAllRead,
}: NotificationCenterProps) {
	const [isOpen, setIsOpen] = useState(false);
	const bellRef = useRef<HTMLButtonElement>(null);
	const panelRef = useRef<HTMLDivElement>(null);

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
		onItemClick(notification);
		close();
	};

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
					notifications={notifications}
					unreadCount={unreadCount}
					page={page}
					totalPages={totalPages}
					onPageChange={onPageChange}
					onItemClick={handleItemClick}
					onMarkAllRead={onMarkAllRead}
				/>
			)}
		</div>
	);
}
