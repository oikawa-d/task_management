import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Calendar } from "./Calendar";

describe("Calendar", () => {
	/**
	 * 期限日のタスクを該当セル内へ表示し、日付とタスクを内部領域で包むことを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 DOMを描画するが、外部状態を変更しない。
	 * @throws 期待するセル構造がない場合にVitestのアサーション例外を送出する。
	 */
	it("期限日のセルにタスクを表示する", () => {
		render(<Calendar month={new Date(2026, 8, 1)} tasks={[{ id: "task-1", project_id: null, title: "期限タスク", due_at: "2026-09-10T03:00:00Z", due_date: "2026-09-10", status: "todo" }]} onPreviousMonth={vi.fn()} onNextMonth={vi.fn()} onRetry={vi.fn()} />);

		const task = screen.getByText("期限タスク");
		expect(task).toBeInTheDocument();
		expect(task.parentElement).toHaveTextContent("10");
		expect(task.parentElement?.className).toContain("tasks");
		expect(task.closest("td")?.className).not.toContain("tasks");
	});

	/**
	 * 当日セルを示し、同一日に属する全タスクを省略せず表示することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 fake timerとDOMを一時的に変更し、finallyでtimerを復元する。
	 * @throws 当日属性またはタスク表示が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("当日を示し、同日のタスクを全件表示する", () => {
		vi.setSystemTime(new Date(2026, 8, 10));
		try {
			render(<Calendar month={new Date(2026, 8, 1)} tasks={[1, 2, 3].map((id) => ({ id: `task-${id}`, project_id: null, title: `タスク${id}`, due_at: "2026-09-10T03:00:00Z", due_date: "2026-09-10", status: "todo" as const }))} onPreviousMonth={vi.fn()} onNextMonth={vi.fn()} onRetry={vi.fn()} />);
			expect(document.querySelector('time[aria-current="date"]')).toHaveAttribute("datetime", "2026-09-10");
			expect(screen.getByText("タスク1")).toBeInTheDocument();
			expect(screen.getByText("タスク2")).toBeInTheDocument();
			expect(screen.getByText("タスク3")).toBeInTheDocument();
			expect(screen.queryByText(/他\d+件/)).not.toBeInTheDocument();
		} finally {
			vi.useRealTimers();
		}
	});

	/**
	 * UTC境界前後のサーバー日付キーが対応するカレンダーセルへ割り当たることを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 TZ環境変数とDOMを一時的に変更し、finallyで環境変数を復元する。
	 * @throws 日付セルの割り当てが期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("サーバーのAPP_TIMEZONE日付キーでUTC境界のタスクを割り当てる", () => {
		vi.stubEnv("TZ", "UTC");
		try {
			render(
				<Calendar
					month={new Date(2026, 8, 1)}
					tasks={[
						{ id: "task-before", project_id: null, title: "境界前タスク", due_at: "2026-09-09T14:59:59Z", due_date: "2026-09-09", status: "todo" },
						{ id: "task-after", project_id: null, title: "境界後タスク", due_at: "2026-09-09T15:00:00Z", due_date: "2026-09-10", status: "todo" },
					]}
					onPreviousMonth={vi.fn()}
					onNextMonth={vi.fn()}
					onRetry={vi.fn()}
				/>,
			);

			expect(screen.getByText("境界前タスク").parentElement).toHaveTextContent("9");
			expect(screen.getByText("境界後タスク").parentElement).toHaveTextContent("10");
		} finally {
			vi.unstubAllEnvs();
		}
	});

	/**
	 * 月送り操作が親から受け取った各callbackを一度ずつ呼び出すことを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 DOMを描画し、mock callbackの呼出回数を更新する。
	 * @throws callback呼出回数が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("月送りボタンを親へ通知する", () => {
		const onPreviousMonth = vi.fn();
		const onNextMonth = vi.fn();
		render(<Calendar month={new Date(2026, 8, 1)} tasks={[]} onPreviousMonth={onPreviousMonth} onNextMonth={onNextMonth} onRetry={vi.fn()} />);

		fireEvent.click(screen.getByRole("button", { name: "前の月" }));
		fireEvent.click(screen.getByRole("button", { name: "次の月" }));
		expect(onPreviousMonth).toHaveBeenCalledOnce();
		expect(onNextMonth).toHaveBeenCalledOnce();
	});
});
