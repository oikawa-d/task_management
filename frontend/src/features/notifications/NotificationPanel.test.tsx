import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotificationPanel } from "./NotificationPanel";
import { buildNotification } from "./testFixtures";

describe("NotificationPanel", () => {
	it("通知が0件のとき空状態メッセージを表示する", () => {
		render(
			<NotificationPanel
				notifications={[]}
				unreadCount={0}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);

		expect(screen.getByText("通知はありません")).toBeInTheDocument();
	});

	it("通知一覧を描画し、行クリックでonItemClickへ通知データを渡す", () => {
		const notification = buildNotification();
		const onItemClick = vi.fn();
		render(
			<NotificationPanel
				notifications={[notification]}
				unreadCount={1}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={onItemClick}
				onMarkAllRead={vi.fn()}
			/>,
		);

		fireEvent.click(screen.getByText("設計書をレビューする"));

		expect(onItemClick).toHaveBeenCalledWith(notification);
	});

	it("未読件数0のとき「すべて既読」ボタンを非活性にする", () => {
		render(
			<NotificationPanel
				notifications={[]}
				unreadCount={0}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);

		expect(screen.getByRole("button", { name: "すべて既読" })).toBeDisabled();
	});

	it("「すべて既読」クリックでonMarkAllReadが呼ばれる", () => {
		const onMarkAllRead = vi.fn();
		render(
			<NotificationPanel
				notifications={[buildNotification()]}
				unreadCount={1}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={onMarkAllRead}
			/>,
		);

		fireEvent.click(screen.getByRole("button", { name: "すべて既読" }));

		expect(onMarkAllRead).toHaveBeenCalledTimes(1);
	});

	it("totalPagesが1のときページネーションを描画しない", () => {
		render(
			<NotificationPanel
				notifications={[buildNotification()]}
				unreadCount={1}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);

		expect(screen.queryByRole("navigation", { name: "通知ページ" })).not.toBeInTheDocument();
	});

	it("totalPagesが2以上のときページネーションを描画し、「次へ」でonPageChangeが呼ばれる", () => {
		const onPageChange = vi.fn();
		render(
			<NotificationPanel
				notifications={[buildNotification()]}
				unreadCount={1}
				page={1}
				totalPages={2}
				onPageChange={onPageChange}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);

		expect(screen.getByRole("button", { name: "前へ" })).toBeDisabled();

		fireEvent.click(screen.getByRole("button", { name: "次へ" }));
		expect(onPageChange).toHaveBeenCalledWith(2);

		fireEvent.click(screen.getByRole("button", { name: "2" }));
		expect(onPageChange).toHaveBeenCalledWith(2);
	});

	it("最終ページでは「前へ」でonPageChangeが呼ばれ、「次へ」は非活性になる", () => {
		const onPageChange = vi.fn();
		render(
			<NotificationPanel
				notifications={[buildNotification()]}
				unreadCount={1}
				page={2}
				totalPages={2}
				onPageChange={onPageChange}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);

		expect(screen.getByRole("button", { name: "次へ" })).toBeDisabled();

		fireEvent.click(screen.getByRole("button", { name: "前へ" }));
		expect(onPageChange).toHaveBeenCalledWith(1);
	});

	it("既読済みと未読の通知で未読マークの見た目が異なる", () => {
		const { rerender } = render(
			<NotificationPanel
				notifications={[buildNotification({ readAt: null })]}
				unreadCount={1}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);
		const unreadMarkClass = screen
			.getByText("設計書をレビューする")
			.closest("button")
			?.querySelector("[aria-hidden]")?.className;

		rerender(
			<NotificationPanel
				notifications={[buildNotification({ readAt: "2026-09-04T02:00:00Z" })]}
				unreadCount={0}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);
		const readMarkClass = screen
			.getByText("設計書をレビューする")
			.closest("button")
			?.querySelector("[aria-hidden]")?.className;

		expect(readMarkClass).not.toBe(unreadMarkClass);
	});

	it("期限未設定の通知は期限行を表示しない", () => {
		render(
			<NotificationPanel
				notifications={[buildNotification({ dueAt: null })]}
				unreadCount={1}
				page={1}
				totalPages={1}
				onPageChange={vi.fn()}
				onItemClick={vi.fn()}
				onMarkAllRead={vi.fn()}
			/>,
		);

		expect(screen.queryByText(/期限/)).not.toBeInTheDocument();
	});
});
