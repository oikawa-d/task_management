import type { CalendarTask } from "../api/types";
import styles from "./Calendar.module.css";

interface CalendarProps {
	month: Date;
	tasks: CalendarTask[];
	isLoading?: boolean;
	isError?: boolean;
	onPreviousMonth: () => void;
	onNextMonth: () => void;
	onRetry: () => void;
}

function dateKey(date: Date): string {
	return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
		.map((part) => String(part).padStart(2, "0"))
		.join("-");
}

function buildDays(month: Date): Date[] {
	const first = new Date(month.getFullYear(), month.getMonth(), 1);
	const start = new Date(first);
	start.setDate(first.getDate() - first.getDay());
	return Array.from({ length: 42 }, (_, index) => {
		const day = new Date(start);
		day.setDate(start.getDate() + index);
		return day;
	});
}

export function Calendar({ month, tasks, isLoading, isError, onPreviousMonth, onNextMonth, onRetry }: CalendarProps) {
	const tasksByDate = new Map<string, CalendarTask[]>();
	for (const task of tasks) {
		const key = task.due_date;
		const grouped = tasksByDate.get(key) ?? [];
		grouped.push(task);
		tasksByDate.set(key, grouped);
	}
	const days = buildDays(month);
	const today = dateKey(new Date());

	return (
		<div className={styles.calendar} aria-label="期限カレンダー">
			<header className={styles.header}>
				<button type="button" onClick={onPreviousMonth} aria-label="前の月">前月</button>
				<h3>{month.toLocaleDateString("ja-JP", { year: "numeric", month: "long" })}</h3>
				<button type="button" onClick={onNextMonth} aria-label="次の月">次月</button>
			</header>
			{isLoading ? <p role="status">カレンダーを読み込み中...</p> : null}
			{isError ? <p role="alert">カレンダーを読み込めませんでした。<button type="button" onClick={onRetry}>再試行</button></p> : null}
			<table className={styles.table}>
				<thead><tr>{["日", "月", "火", "水", "木", "金", "土"].map((label) => <th key={label}>{label}</th>)}</tr></thead>
				<tbody>
					{Array.from({ length: 6 }, (_, week) => (
						<tr key={week}>
							{days.slice(week * 7, week * 7 + 7).map((day) => {
								const dayTasks = tasksByDate.get(dateKey(day)) ?? [];
								const key = dateKey(day);
								const dayClass = day.getMonth() === month.getMonth() ? styles.day : `${styles.day} ${styles.otherMonth}`;
								return <td className={`${dayClass} ${styles.tasks} ${key === today ? styles.today : ""}`} key={key}><time dateTime={key} aria-current={key === today ? "date" : undefined}>{day.getDate()}</time>{dayTasks.map((task) => <span className={styles.task} key={task.id}>{task.title}</span>)}</td>;
							})}
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
