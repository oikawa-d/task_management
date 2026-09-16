export interface MarkAllReadButtonProps {
	unreadCount: number;
	onClick: () => void;
}

/** 「すべて既読」ボタン。未読件数が0のときは非活性にする */
export function MarkAllReadButton({ unreadCount, onClick }: MarkAllReadButtonProps) {
	return (
		<button type="button" onClick={onClick} disabled={unreadCount === 0}>
			すべて既読
		</button>
	);
}
