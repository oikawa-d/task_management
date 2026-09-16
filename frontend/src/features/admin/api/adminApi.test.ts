import { afterEach, describe, expect, it, vi } from "vitest";

import { setAuthAdapterMode, clearAuthAdapter } from "../../../api/authAdapter/client";
import { listAdminUsers } from "./adminApi";

describe("adminApi", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
		clearAuthAdapter();
	});

	it("ユーザー検索・権限・状態フィルタをAPI契約のsnake_caseへ変換する", async () => {
		setAuthAdapterMode("session");
		const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } }), { status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await listAdminUsers({ page: 2, perPage: 20, q: "taro", role: "admin", isActive: "false" });

		expect(fetchMock).toHaveBeenCalledOnce();
		const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(url).toContain("/api/admin/users?");
		expect(new URL(url, "http://localhost").searchParams).toEqual(new URLSearchParams("page=2&per_page=20&q=taro&role=admin&is_active=false"));
	});
});
