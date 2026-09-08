import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as unreadCountApi from "../api/unreadCountApi";
import { UnreadCountFetchError } from "../api/unreadCountApi";
import { useUnreadCount } from "./useUnreadCount";

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, gcTime: 0 } },
	});
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("useUnreadCount", () => {
	beforeEach(() => {
		vi.stubEnv("VITE_NOTIFICATION_POLL_INTERVAL_MS", "1000");
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllEnvs();
		vi.restoreAllMocks();
	});

	it("設定されたポーリング間隔で未読件数を再取得する", async () => {
		const fetchSpy = vi
			.spyOn(unreadCountApi, "fetchUnreadCount")
			.mockResolvedValue({ unread_count: 2 });

		const { result } = renderHook(() => useUnreadCount({ isAuthenticated: true }), {
			wrapper: createWrapper(),
		});

		await act(async () => {
			await vi.advanceTimersByTimeAsync(0);
		});
		expect(result.current.data).toBe(2);
		expect(fetchSpy).toHaveBeenCalledTimes(1);

		await act(async () => {
			await vi.advanceTimersByTimeAsync(1000);
		});
		expect(fetchSpy).toHaveBeenCalledTimes(2);

		await act(async () => {
			await vi.advanceTimersByTimeAsync(1000);
		});
		expect(fetchSpy).toHaveBeenCalledTimes(3);
	});

	it("未認証時はポーリングを行わない", async () => {
		const fetchSpy = vi
			.spyOn(unreadCountApi, "fetchUnreadCount")
			.mockResolvedValue({ unread_count: 5 });

		const { result } = renderHook(() => useUnreadCount({ isAuthenticated: false }), {
			wrapper: createWrapper(),
		});

		await vi.advanceTimersByTimeAsync(5000);

		expect(fetchSpy).not.toHaveBeenCalled();
		expect(result.current.data).toBeUndefined();
		expect(result.current.fetchStatus).toBe("idle");
	});

	it("fetchUnreadCountが401で失敗した場合はリトライせずisErrorになる", async () => {
		const fetchSpy = vi
			.spyOn(unreadCountApi, "fetchUnreadCount")
			.mockRejectedValue(new UnreadCountFetchError(401));

		const { result } = renderHook(() => useUnreadCount({ isAuthenticated: true }), {
			wrapper: createWrapper(),
		});

		await act(async () => {
			await vi.advanceTimersByTimeAsync(0);
		});

		expect(result.current.isError).toBe(true);
		expect(fetchSpy).toHaveBeenCalledTimes(1);

		// 401はretry: falseのため、ポーリング間隔が経過してもリトライは増えず、
		// 次のポーリングタイミングでのみ再実行される。
		await act(async () => {
			await vi.advanceTimersByTimeAsync(1000);
		});
		expect(fetchSpy).toHaveBeenCalledTimes(2);
	});

	it("fetchUnreadCountが401以外のエラーで失敗した場合はリトライしてもisErrorになる", async () => {
		// retryの指数バックオフとrefetchIntervalが同一タイムラインで干渉しないよう、
		// このテストのみポーリング間隔を十分大きくする。
		vi.stubEnv("VITE_NOTIFICATION_POLL_INTERVAL_MS", "100000");
		const fetchSpy = vi
			.spyOn(unreadCountApi, "fetchUnreadCount")
			.mockRejectedValue(new unreadCountApi.UnreadCountFetchError(503));

		const { result } = renderHook(() => useUnreadCount({ isAuthenticated: true }), {
			wrapper: createWrapper(),
		});

		// 初回 + retry最大3回（指数バックオフ）が完了するのに十分な時間だけ進める。
		await act(async () => {
			await vi.advanceTimersByTimeAsync(30000);
		});

		expect(result.current.isError).toBe(true);
		// 初回 + retry最大3回 = 4回呼ばれる
		expect(fetchSpy).toHaveBeenCalledTimes(4);
	});

	it("ネットワークエラー（statusを持たない例外）の場合はリトライしたうえでisErrorになる", async () => {
		// retryの指数バックオフとrefetchIntervalが同一タイムラインで干渉しないよう、
		// このテストのみポーリング間隔を十分大きくする。
		vi.stubEnv("VITE_NOTIFICATION_POLL_INTERVAL_MS", "100000");
		const fetchSpy = vi
			.spyOn(unreadCountApi, "fetchUnreadCount")
			.mockRejectedValue(new TypeError("Failed to fetch"));

		const { result } = renderHook(() => useUnreadCount({ isAuthenticated: true }), {
			wrapper: createWrapper(),
		});

		await act(async () => {
			await vi.advanceTimersByTimeAsync(30000);
		});

		expect(result.current.isError).toBe(true);
		// UnreadCountFetchErrorではないため401判定に該当せず、初回 + retry最大3回 = 4回呼ばれる
		expect(fetchSpy).toHaveBeenCalledTimes(4);
	});

	it("queryFnにAbortSignalを渡してfetchUnreadCountへ伝搬する", async () => {
		const fetchSpy = vi
			.spyOn(unreadCountApi, "fetchUnreadCount")
			.mockResolvedValue({ unread_count: 1 });

		renderHook(() => useUnreadCount({ isAuthenticated: true }), {
			wrapper: createWrapper(),
		});

		await act(async () => {
			await vi.advanceTimersByTimeAsync(0);
		});

		expect(fetchSpy).toHaveBeenCalledWith(expect.any(AbortSignal));
	});
});
