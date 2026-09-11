import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { useAuthStore } from "../../../auth/authStore";
import { useRegister } from "./useRegister";

function createWrapper() {
	const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
	return function Wrapper({ children }: PropsWithChildren) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("useRegister", () => {
	afterEach(() => {
		clearAuthAdapter();
		useAuthStore.getState().reset();
		vi.unstubAllGlobals();
	});

	it("成功時はPOST /auth/registerを呼び、RegisterResponseを返す。authStoreは更新しない（自動ログインしない）", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			status: 201,
			json: () => Promise.resolve({ id: "u1", email: "taro@example.com", message: "確認メールを送信しました。" }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useRegister(), { wrapper: createWrapper() });

		const response = await result.current.mutateAsync({
			last_name: "山田",
			first_name: "太郎",
			last_name_kana: "ヤマダ",
			first_name_kana: "タロウ",
			email: "taro@example.com",
			username: "taro123",
			password: "Password1!",
			password_confirm: "Password1!",
			birth_date: "2000-01-01",
		});

		expect(response).toEqual({ id: "u1", email: "taro@example.com", message: "確認メールを送信しました。" });
		expect(useAuthStore.getState().status).not.toBe("authenticated");
	});

	it("409 DUPLICATE_EMAILはApiErrorのままthrowする", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 409,
			headers: new Headers(),
			json: () => Promise.resolve({ error: { code: "DUPLICATE_EMAIL", message: "このメールアドレスは既に登録されています" } }),
		});
		vi.stubGlobal("fetch", fetchMock);

		const { result } = renderHook(() => useRegister(), { wrapper: createWrapper() });

		await expect(
			result.current.mutateAsync({
				last_name: "山田",
				first_name: "太郎",
				last_name_kana: "ヤマダ",
				first_name_kana: "タロウ",
				email: "taro@example.com",
				username: "taro123",
				password: "Password1!",
				password_confirm: "Password1!",
				birth_date: "2000-01-01",
			}),
		).rejects.toMatchObject({ code: "DUPLICATE_EMAIL" });
	});
});
