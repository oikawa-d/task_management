import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../../api/authAdapter/client";
import { getLoginHistory } from "./loginHistoryApi";

describe("loginHistoryApi", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("本人のログイン履歴エンドポイントをfetchWithAuth経由で呼ぶ", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], meta: { limit: 50, count: 0 } }), { status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await expect(getLoginHistory()).resolves.toEqual({ items: [], meta: { limit: 50, count: 0 } });
		expect(fetchMock).toHaveBeenCalledWith("/api/users/me/login-history", expect.objectContaining({ credentials: "include" }));
	});
});
