import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchUnreadCount, UnreadCountFetchError } from "./unreadCountApi";

describe("fetchUnreadCount", () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it("正常時はunread_countを含むレスポンスを返す", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ unread_count: 3 }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await fetchUnreadCount();

		expect(result).toEqual({ unread_count: 3 });
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/notifications/unread-count",
			expect.objectContaining({ method: "GET", credentials: "include" }),
		);
	});

	it("レスポンスが200以外の場合はUnreadCountFetchErrorを投げる", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 401,
			json: () => Promise.resolve({}),
		});
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchUnreadCount()).rejects.toThrow("failed to fetch unread count: 401");

		const error = await fetchUnreadCount().catch((e: unknown) => e);
		expect(error).toBeInstanceOf(UnreadCountFetchError);
		expect((error as UnreadCountFetchError).status).toBe(401);
	});

	it("AbortSignalをfetchへ伝搬する", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ unread_count: 0 }),
		});
		vi.stubGlobal("fetch", fetchMock);
		const controller = new AbortController();

		await fetchUnreadCount(controller.signal);

		expect(fetchMock).toHaveBeenCalledWith(
			"/api/notifications/unread-count",
			expect.objectContaining({ signal: controller.signal }),
		);
	});
});
