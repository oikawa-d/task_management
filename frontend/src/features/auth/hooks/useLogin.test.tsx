import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useAuthStore } from "../../../auth/authStore";
import { useLogin } from "./useLogin";

function createWrapper() {
	const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
	return function Wrapper({ children }: PropsWithChildren) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("useLogin", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
	});

	afterEach(() => {
		clearAuthAdapter();
		useAuthStore.getState().reset();
		vi.unstubAllGlobals();
	});

	it("成功時はPOST /auth/loginを呼び、GET /auth/meで取得したユーザーでauthStoreをauthenticatedへ更新する", async () => {
		const fetchMock = vi.fn().mockImplementation((url: string) => {
			if (url.endsWith("/auth/login")) {
				return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
			}
			if (url.endsWith("/auth/me")) {
				return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: "u1", role: "member" }) });
			}
			throw new Error(`unexpected url: ${url}`);
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

		await result.current.mutateAsync({ identifier: "taro", password: "password1" });

		await waitFor(() => expect(useAuthStore.getState().status).toBe("authenticated"));
		expect(useAuthStore.getState().user).toEqual({ id: "u1", role: "member" });
	});

	it("401 INVALID_CREDENTIALSはApiErrorのままthrowし、authStoreを更新しない", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 401,
			headers: new Headers(),
			json: () => Promise.resolve({ error: { code: "INVALID_CREDENTIALS", message: "IDまたはパスワードが正しくありません" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

		await expect(result.current.mutateAsync({ identifier: "taro", password: "wrong" })).rejects.toMatchObject({
			code: "INVALID_CREDENTIALS",
		});
		expect(useAuthStore.getState().status).not.toBe("authenticated");
	});
});
