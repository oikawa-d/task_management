import styles from "./BirthDateSelect.module.css";

/** design doc: docs/detailed_design/screen/02_register.md §3⑥⑦⑧、要検討=選択範囲は画面側の目安（現在年から100年前まで） */
const YEARS_BACK = 100;

export interface BirthDateSelectProps {
	year: string;
	month: string;
	day: string;
	onChange: (next: { year: string; month: string; day: string }) => void;
}

/** design doc: docs/detailed_design/screen/02_register.md §9.3 getDaysInMonth */
export function getDaysInMonth(year: number | undefined, month: number | undefined): number {
	if (!year || !month) {
		return 31;
	}
	return new Date(year, month, 0).getDate();
}

export function BirthDateSelect({ year, month, day, onChange }: BirthDateSelectProps) {
	const currentYear = new Date().getFullYear();
	const years = range(currentYear - YEARS_BACK, currentYear);
	const months = range(1, 12);
	const days = range(1, getDaysInMonth(Number(year) || undefined, Number(month) || undefined));

	return (
		<div className={styles.group}>
			<label className={styles.field}>
				<span>年</span>
				<select
					aria-label="年"
					value={year}
					onChange={(event) => onChange({ year: event.target.value, month, day })}
				>
					<option value="">未選択</option>
					{years.map((y) => (
						<option key={y} value={String(y)}>{y}</option>
					))}
				</select>
			</label>
			<label className={styles.field}>
				<span>月</span>
				<select
					aria-label="月"
					value={month}
					onChange={(event) => onChange({ year, month: event.target.value, day })}
				>
					<option value="">未選択</option>
					{months.map((m) => (
						<option key={m} value={String(m)}>{m}</option>
					))}
				</select>
			</label>
			<label className={styles.field}>
				<span>日</span>
				<select
					aria-label="日"
					value={day}
					disabled={!year || !month}
					onChange={(event) => onChange({ year, month, day: event.target.value })}
				>
					<option value="">未選択</option>
					{days.map((d) => (
						<option key={d} value={String(d)}>{d}</option>
					))}
				</select>
			</label>
		</div>
	);
}

function range(start: number, end: number): number[] {
	const result: number[] = [];
	for (let value = start; value <= end; value += 1) {
		result.push(value);
	}
	return result;
}
