import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useHashToken } from "./useHashToken";

function setHash(hash: string) {
	window.history.replaceState(null, "", `/some/path${hash}`);
}

describe("useHashToken", () => {
	afterEach(() => {
		window.history.replaceState(null, "", "/");
		vi.restoreAllMocks();
	});

	it("fragmentからtokenを抽出し、history.replaceStateでURLから除去する", () => {
		setHash("#token=abc123");
		const replaceStateSpy = vi.spyOn(window.history, "replaceState");

		const { result } = renderHook(() => useHashToken());

		expect(result.current.ready).toBe(true);
		expect(result.current.token).toBe("abc123");
		expect(replaceStateSpy).toHaveBeenCalledTimes(1);
		expect(replaceStateSpy).toHaveBeenCalledWith(null, "", "/some/path");
	});

	it("除去後はURL・履歴のどちらにもtokenが残らない", () => {
		setHash("#token=secret-token");

		renderHook(() => useHashToken());

		expect(window.location.hash).toBe("");
		expect(window.location.href).not.toContain("secret-token");
	});

	it("tokenがない場合はnullを返し、history.replaceStateを呼ばない", () => {
		setHash("");
		const replaceStateSpy = vi.spyOn(window.history, "replaceState");

		const { result } = renderHook(() => useHashToken());

		expect(result.current.ready).toBe(true);
		expect(result.current.token).toBeNull();
		expect(replaceStateSpy).not.toHaveBeenCalled();
	});

	it("StrictModeの二重effect実行相当でもreplaceStateは1回のみ呼ばれる", () => {
		setHash("#token=double-mount");
		const replaceStateSpy = vi.spyOn(window.history, "replaceState");

		const { result, rerender } = renderHook(() => useHashToken());
		act(() => {
			rerender();
			rerender();
		});

		expect(result.current.token).toBe("double-mount");
		expect(replaceStateSpy).toHaveBeenCalledTimes(1);
	});
});
