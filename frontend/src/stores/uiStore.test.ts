import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useUiStore } from "./uiStore";

describe("uiStore theme", () => {
	afterEach(() => {
		useUiStore.getState().setTheme("light");
		useUiStore.setState({ theme: "system", fontScale: 1 });
		document.documentElement.removeAttribute("data-theme");
		localStorage.clear();
	});

	/**
	 * light/darkを選択した条件でdata-themeとlocalStorageが即時更新されることを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 uiStore、DOM、localStorageを一時的に変更する。
	 * @throws テーマ属性または永続化値が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("light/darkをdata-themeへ即時反映する", () => {
		const { result } = renderHook(() => useUiStore());
		act(() => result.current.setTheme("dark"));
		expect(document.documentElement.dataset.theme).toBe("dark");
		act(() => result.current.setTheme("light"));
		expect(document.documentElement.dataset.theme).toBe("light");
		expect(JSON.parse(localStorage.getItem("cerberus.ui") ?? "{}").state.theme).toBe("light");
	});

	/**
	 * systemを選択した条件でdata-themeを削除し、store状態をsystemに保持することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 uiStoreとdocumentのdata-theme属性を一時的に変更する。
	 * @throws テーマ状態または属性が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("systemではdata-themeを外し、状態を保持する", () => {
		document.documentElement.dataset.theme = "dark";
		const { result } = renderHook(() => useUiStore());
		act(() => result.current.setTheme("system"));
		expect(result.current.theme).toBe("system");
		expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
	});

	/**
	 * 保存済みテーマをrehydrateした条件でstoreとdata-themeへ復元することを検証する。
	 * @param なし。
	 * @returns 非同期検証処理を表すPromise。
	 * @副作用 localStorage、uiStore、documentを一時的に変更する。
	 * @throws 復元値が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("保存済みthemeをrehydrateしてdata-themeへ反映する", async () => {
		localStorage.setItem("cerberus.ui", JSON.stringify({ state: { fontScale: 1.15, theme: "dark" }, version: 0 }));
		await act(async () => {
			await useUiStore.persist.rehydrate();
		});
		expect(useUiStore.getState().theme).toBe("dark");
		expect(useUiStore.getState().fontScale).toBe(1.15);
		expect(document.documentElement.dataset.theme).toBe("dark");
	});

	/**
	 * system選択時にmatchMedia listenerを登録し、明示テーマ選択時に解除することを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 matchMedia mock、uiStore、documentを一時的に変更する。
	 * @throws listenerの登録・解除が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("system themeのmatchMedia listenerを登録し、明示テーマで解除する", () => {
		const addEventListener = vi.fn();
		const removeEventListener = vi.fn();
		const media = { addEventListener, removeEventListener } as unknown as MediaQueryList;
		Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => media) });
		useUiStore.getState().setTheme("system");
		expect(addEventListener).toHaveBeenCalledOnce();
		document.documentElement.dataset.theme = "dark";
		const handleChange = addEventListener.mock.calls[0]?.[1] as (() => void) | undefined;
		handleChange?.();
		expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
		useUiStore.getState().setTheme("dark");
		expect(removeEventListener).toHaveBeenCalledOnce();
	});

	/**
	 * addListener/removeListenerしかない旧APIでもsystem listenerを解除できることを検証する。
	 * @param なし。
	 * @returns なし。
	 * @副作用 matchMedia mock、uiStore、documentを一時的に変更する。
	 * @throws listenerの登録・解除が期待と異なる場合にVitestのアサーション例外を送出する。
	 */
	it("旧matchMedia APIでもsystem listenerを解除できる", () => {
		const addListener = vi.fn();
		const removeListener = vi.fn();
		const media = { addListener, removeListener } as unknown as MediaQueryList;
		Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => media) });
		useUiStore.getState().setTheme("system");
		useUiStore.getState().setTheme("light");
		expect(addListener).toHaveBeenCalledOnce();
		expect(removeListener).toHaveBeenCalledOnce();
	});
});
