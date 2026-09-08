import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotificationBell } from "./NotificationBell";

describe("NotificationBell", () => {
	it("未読件数が1件以上のときバッジを件数通り表示する", () => {
		render(<NotificationBell unreadCount={3} isOpen={false} onClick={vi.fn()} />);

		expect(screen.getByLabelText("未読 3 件")).toHaveTextContent("3");
	});

	it("未読件数が100件以上のとき 99+ と表示する", () => {
		render(<NotificationBell unreadCount={150} isOpen={false} onClick={vi.fn()} />);

		expect(screen.getByLabelText("未読 150 件")).toHaveTextContent("99+");
	});

	it("未読件数が0のときバッジを表示しない", () => {
		render(<NotificationBell unreadCount={0} isOpen={false} onClick={vi.fn()} />);

		expect(screen.queryByText(/未読/)).not.toBeInTheDocument();
	});

	it("isOpenの値をaria-expandedへ反映する", () => {
		render(<NotificationBell unreadCount={0} isOpen={true} onClick={vi.fn()} />);

		expect(screen.getByRole("button", { name: "通知" })).toHaveAttribute("aria-expanded", "true");
	});

	it("クリックでonClickが呼ばれる", () => {
		const onClick = vi.fn();
		render(<NotificationBell unreadCount={0} isOpen={false} onClick={onClick} />);

		fireEvent.click(screen.getByRole("button", { name: "通知" }));

		expect(onClick).toHaveBeenCalledTimes(1);
	});
});
