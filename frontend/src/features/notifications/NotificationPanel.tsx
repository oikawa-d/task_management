import { forwardRef } from "react";

import { MarkAllReadButton } from "./MarkAllReadButton";
import { NotificationItem } from "./NotificationItem";
import { NotificationPagination } from "./NotificationPagination";
import styles from "./NotificationPanel.module.css";
import type { NotificationItemData } from "./types";

export interface NotificationPanelProps {
	notifications: NotificationItemData[];
	unreadCount: number;
	page: number;
	totalPages: number;
	onPageChange: (page: number) => void;
	onItemClick: (notification: NotificationItemData) => void;
	onMarkAllRead: () => void;
}

/**
 * 通知一覧ポップオーバー。開閉状態は持たず、表示するデータとコールバックのみを
 * propsで受け取る（未読件数・一覧取得・既読化APIの呼び出しは呼び出し側の責務）。
 */
export const NotificationPanel = forwardRef<HTMLDivElement, NotificationPanelProps>(
	function NotificationPanel(
		{ notifications, unreadCount, page, totalPages, onPageChange, onItemClick, onMarkAllRead },
		ref,
	) {
		return (
			<div ref={ref} role="dialog" aria-label="通知" className={styles.panel}>
				<div className={styles.header}>
					<span>通知</span>
					<MarkAllReadButton unreadCount={unreadCount} onClick={onMarkAllRead} />
				</div>

				{notifications.length === 0 ? (
					<p className={styles.empty}>通知はありません</p>
				) : (
					<ul className={styles.list}>
						{notifications.map((notification) => (
							<NotificationItem
								key={notification.id}
								notification={notification}
								onClick={onItemClick}
							/>
						))}
					</ul>
				)}

				{totalPages >= 2 && (
					<div className={styles.footer}>
						<NotificationPagination page={page} totalPages={totalPages} onPageChange={onPageChange} />
					</div>
				)}
			</div>
		);
	},
);
