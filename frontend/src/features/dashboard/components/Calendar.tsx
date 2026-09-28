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

/**
 * Dateをカレンダーの日付キーへ変換する。
 * @param date 変換対象の日付。
 * @returns `YYYY-MM-DD`形式の日付キー。
 * @副作用 なし。
 * @throws なし。
 */
function dateKey(date: Date): string {
	return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
		.map((part) => String(part).padStart(2, "0"))
		.join("-");
}

/**
 * 対象月を含む42日分のカレンダー表示日を生成する。
 * @param month 表示対象月。
 * @returns 日曜始まり6週分の日付配列。
 * @副作用 なし。
 * @throws なし。
 */
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

/**
 * 月間カレンダーと日付ごとの全タスクを描画する。
 * @param props 表示月、タスク、状態表示、月移動・再試行callback。
 * @returns カレンダーのReact要素。
 * @副作用 callback実行時に親コンポーネントへ操作を通知する。
 * @throws 描画中にReactまたは日付処理のエラーが発生した場合はReactへ伝播する。
 */
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
								return (
									<td className={`${dayClass} ${key === today ? styles.today : ""}`} key={key}>
										<div className={styles.tasks}>
											<time dateTime={key} aria-current={key === today ? "date" : undefined}>{day.getDate()}</time>
											{dayTasks.map((task) => <span className={styles.task} key={task.id}>{task.title}</span>)}
										</div>
									</td>
								);
							})}
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
