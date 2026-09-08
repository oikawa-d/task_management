import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as unreadCountApi from "../api/unreadCountApi";
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
});
