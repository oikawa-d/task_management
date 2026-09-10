import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useAuthMeQuery } from "./useAuthMeQuery";

function createWrapper() {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: PropsWithChildren) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("useAuthMeQuery", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("refetchで最新のユーザー情報を取得する", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () => Promise.resolve({ id: "user-1", role: "member", profile_completed: false }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useAuthMeQuery(), { wrapper: createWrapper() });

		const me = await result.current.refetch();

		expect(me).toEqual({ id: "user-1", role: "member", profile_completed: false });
	});

	it("401等の失敗時は例外をそのままthrowする", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 401,
			json: () => Promise.resolve({ error: { code: "UNAUTHENTICATED" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useAuthMeQuery(), { wrapper: createWrapper() });

		await expect(result.current.refetch()).rejects.toMatchObject({ status: 401 });
	});
});
