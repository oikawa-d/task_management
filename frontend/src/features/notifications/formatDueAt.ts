/** 通知行に表示する期限日時を "MM/DD HH:mm" 形式へ整形する */
export function formatDueAt(dueAt: string): string {
	const date = new Date(dueAt);
	const month = String(date.getMonth() + 1).padStart(2, "0");
	const day = String(date.getDate()).padStart(2, "0");
	const hours = String(date.getHours()).padStart(2, "0");
	const minutes = String(date.getMinutes()).padStart(2, "0");
	return `${month}/${day} ${hours}:${minutes}`;
}
