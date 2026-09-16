import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useOAuthExchange } from "./useOAuthExchange";

function createWrapper() {
	const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
	return function Wrapper({ children }: PropsWithChildren) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("useOAuthExchange", () => {
	beforeEach(() => {
		setAuthAdapterMode("jwt");
	});

	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("成功時はaccess_tokenを含むレスポンスを返しTokenStoreへ保存する", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			json: () =>
				Promise.resolve({
					access_token: "token-abc",
					token_type: "bearer",
					expires_in: 900,
					redirect_to: "/projects/1",
				}),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useOAuthExchange(), { wrapper: createWrapper() });

		const response = await result.current.mutateAsync({ code: "handoff-code" });

		expect(response.redirect_to).toBe("/projects/1");

		// 保存されたaccessTokenは以降のfetchWithAuth呼び出しでAuthorizationヘッダとして使われる
		fetchMock.mockClear();
		fetchMock.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
		const { fetchWithAuth } = await import("../../../api/authAdapter/client");
		await fetchWithAuth("/api/auth/me", { method: "GET" });
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/auth/me",
			expect.objectContaining({ headers: expect.any(Headers) }),
		);
		const sentHeaders = fetchMock.mock.calls[0][1].headers as Headers;
		expect(sentHeaders.get("authorization")).toBe("Bearer token-abc");
	});

	it("失敗時はエラーをそのままthrowする", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 400,
			json: () => Promise.resolve({ error: { code: "OAUTH_HANDOFF_INVALID" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useOAuthExchange(), { wrapper: createWrapper() });

		await expect(result.current.mutateAsync({ code: "expired" })).rejects.toMatchObject({
			code: "OAUTH_HANDOFF_INVALID",
		});
		await waitFor(() => expect(result.current.isError).toBe(true));
	});
});
