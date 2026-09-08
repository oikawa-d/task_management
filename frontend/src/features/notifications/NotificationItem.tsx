import { formatDueAt } from "./formatDueAt";
import styles from "./NotificationItem.module.css";
import type { NotificationItemData } from "./types";

export interface NotificationItemProps {
	notification: NotificationItemData;
	/**
	 * 行クリック時のコールバック。遷移可否（task削除済みか）や既読化APIの呼び出しは
	 * 呼び出し側（state管理側）の責務とし、本コンポーネントは通知データを渡すのみ。
	 */
	onClick: (notification: NotificationItemData) => void;
}

/** 通知パネル内の1行。未読マーク・タイトル・期限を表示する */
export function NotificationItem({ notification, onClick }: NotificationItemProps) {
	const isUnread = notification.readAt === null;

	return (
		<li>
			<button type="button" className={styles.row} onClick={() => onClick(notification)}>
				<span
					aria-hidden="true"
					className={isUnread ? styles.unreadMark : styles.unreadMarkPlaceholder}
				/>
				<span className={styles.body}>
					<p className={styles.title}>{notification.title}</p>
					{notification.dueAt && (
						<p className={styles.due}>期限 {formatDueAt(notification.dueAt)}</p>
					)}
				</span>
			</button>
		</li>
	);
}
