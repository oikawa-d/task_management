import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotificationCenter } from "./NotificationCenter";
import { buildNotification } from "./testFixtures";

const apiMocks = vi.hoisted(() => ({
	getNotifications: vi.fn(),
	markNotificationRead: vi.fn(),
	markAllNotificationsRead: vi.fn(),
}));

vi.mock("./api/notificationsApi", () => apiMocks);

function renderCenter(overrides: Partial<Parameters<typeof NotificationCenter>[0]> = {}) {
	const props = {
		unreadCount: 0,
		notifications: [],
		page: 1,
		totalPages: 1,
		onPageChange: vi.fn(),
		onItemClick: vi.fn(),
		onMarkAllRead: vi.fn(),
		...overrides,
	};
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	const utils = render(<QueryClientProvider client={queryClient}><NotificationCenter {...props} /></QueryClientProvider>);
	return { ...utils, props };
}

describe("NotificationCenter", () => {
	it("未読バッジが件数通り表示される", () => {
		renderCenter({ unreadCount: 3 });

		expect(screen.getByLabelText("未読 3 件")).toHaveTextContent("3");
	});

	it("全既読操作でバッジが消える（unreadCountが0へ更新された場合）", () => {
		const { rerender, props } = renderCenter({ unreadCount: 2 });
		expect(screen.getByLabelText("未読 2 件")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		fireEvent.click(screen.getByRole("button", { name: "すべて既読" }));
		expect(props.onMarkAllRead).toHaveBeenCalledTimes(1);

		const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
		rerender(<QueryClientProvider client={queryClient}><NotificationCenter {...props} unreadCount={0} /></QueryClientProvider>);

		expect(screen.queryByText(/未読/)).not.toBeInTheDocument();
	});

	it("ベルクリックでパネルが開閉する", () => {
		renderCenter();

		expect(screen.queryByRole("dialog", { name: "通知" })).not.toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		expect(screen.getByRole("dialog", { name: "通知" })).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		expect(screen.queryByRole("dialog", { name: "通知" })).not.toBeInTheDocument();
	});

	it("Escapeキーでパネルを閉じ、ベルへフォーカスを戻す", () => {
		renderCenter();

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		expect(screen.getByRole("dialog", { name: "通知" })).toBeInTheDocument();

		fireEvent.keyDown(document, { key: "Escape" });

		expect(screen.queryByRole("dialog", { name: "通知" })).not.toBeInTheDocument();
		expect(screen.getByRole("button", { name: "通知" })).toHaveFocus();
	});

	it("パネル内側のクリックではパネルを閉じない", () => {
		renderCenter();

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		const panel = screen.getByRole("dialog", { name: "通知" });

		fireEvent.mouseDown(panel);

		expect(screen.getByRole("dialog", { name: "通知" })).toBeInTheDocument();
	});

	it("外側クリックでパネルを閉じる", () => {
		renderCenter();

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		expect(screen.getByRole("dialog", { name: "通知" })).toBeInTheDocument();

		fireEvent.mouseDown(document.body);

		expect(screen.queryByRole("dialog", { name: "通知" })).not.toBeInTheDocument();
	});

	it("通知行クリックでonItemClickを呼び、パネルを閉じる", () => {
		const notification = buildNotification();
		const { props } = renderCenter({ notifications: [notification], unreadCount: 1 });

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		fireEvent.click(screen.getByText(notification.title));

		expect(props.onItemClick).toHaveBeenCalledWith(notification);
		expect(screen.queryByRole("dialog", { name: "通知" })).not.toBeInTheDocument();
	});

	it("既読API失敗時はパネルを維持して再試行できる", async () => {
		const notification = buildNotification({ readAt: null });
		apiMocks.getNotifications.mockResolvedValue({ items: [notification], totalPages: 1 });
		apiMocks.markNotificationRead.mockRejectedValueOnce(new Error("network"));
		apiMocks.markNotificationRead.mockResolvedValueOnce({ unreadCount: 0 });
		const { props } = renderCenter({ unreadCount: 1, notifications: undefined, enableDataApi: true });

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		fireEvent.click(await screen.findByText(notification.title));

		await screen.findByRole("alert");
		expect(screen.getByRole("dialog", { name: "通知" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "再試行" }));

		await waitFor(() => expect(props.onItemClick).toHaveBeenCalledWith(notification));
		expect(apiMocks.markNotificationRead).toHaveBeenCalledTimes(2);
	});

	it("全件既読API失敗時は親の件数を更新せず再試行できる", async () => {
		apiMocks.markAllNotificationsRead.mockRejectedValueOnce(new Error("network"));
		apiMocks.markAllNotificationsRead.mockResolvedValueOnce({ unreadCount: 0 });
		const { props } = renderCenter({ unreadCount: 2, notifications: undefined, enableDataApi: true });

		fireEvent.click(screen.getByRole("button", { name: "通知" }));
		fireEvent.click(screen.getByRole("button", { name: "すべて既読" }));

		await screen.findByRole("alert");
		expect(props.onMarkAllRead).not.toHaveBeenCalled();
		fireEvent.click(screen.getByRole("button", { name: "再試行" }));

		await waitFor(() => expect(props.onMarkAllRead).toHaveBeenCalledTimes(1));
	});
});
