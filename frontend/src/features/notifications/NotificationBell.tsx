import { forwardRef } from "react";

import styles from "./NotificationBell.module.css";

const MAX_DISPLAYED_COUNT = 99;

export interface NotificationBellProps {
	/** 未読通知件数。0のときはバッジを表示しない */
	unreadCount: number;
	/** 通知パネルが開いているか（aria-expandedへ反映） */
	isOpen: boolean;
	/** ベルクリック時のコールバック（パネルの開閉はNotificationCenter側で管理） */
	onClick: () => void;
}

function formatBadgeLabel(count: number): string {
	return count > MAX_DISPLAYED_COUNT ? `${MAX_DISPLAYED_COUNT}+` : String(count);
}

/**
 * ヘッダーに表示する通知ベルアイコン。未読件数バッジの表示のみを担い、
 * 未読件数の取得ロジックは持たない（props経由で注入される）。
 */
export const NotificationBell = forwardRef<HTMLButtonElement, NotificationBellProps>(
	function NotificationBell({ unreadCount, isOpen, onClick }, ref) {
		const hasUnread = unreadCount >= 1;

		return (
			<button
				ref={ref}
				type="button"
				className={styles.bellButton}
				aria-label="通知"
				aria-expanded={isOpen}
				onClick={onClick}
			>
				<span aria-hidden="true">🔔</span>
				{hasUnread && (
					<span className={styles.badge} aria-label={`未読 ${unreadCount} 件`}>
						{formatBadgeLabel(unreadCount)}
					</span>
				)}
			</button>
		);
	},
);
