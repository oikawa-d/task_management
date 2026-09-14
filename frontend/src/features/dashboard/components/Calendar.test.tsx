import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Calendar } from "./Calendar";

describe("Calendar", () => {
	it("期限日のセルにタスクを表示する", () => {
		render(<Calendar month={new Date(2026, 8, 1)} tasks={[{ id: "task-1", project_id: null, title: "期限タスク", due_at: "2026-09-10T03:00:00Z", due_date: "2026-09-10", status: "todo" }]} onPreviousMonth={vi.fn()} onNextMonth={vi.fn()} onRetry={vi.fn()} />);

		expect(screen.getByText("期限タスク")).toBeInTheDocument();
		expect(screen.getByText("期限タスク").parentElement).toHaveTextContent("10");
	});

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
