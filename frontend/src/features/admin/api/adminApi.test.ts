import axios, { type AxiosInstance } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetApiClient } from "../../../api/client";
import { listAdminUsers } from "./adminApi";

describe("adminApi", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		resetApiClient();
	});

	it("ユーザー検索・権限・状態フィルタをAPI契約のsnake_caseへ変換する", async () => {
		const client = { get: vi.fn().mockResolvedValue({ data: { items: [], meta: { page: 1, per_page: 20, total: 0, total_pages: 0 } } }), interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } } as unknown as AxiosInstance;
		vi.spyOn(axios, "create").mockReturnValue(client);

		await listAdminUsers({ page: 2, perPage: 20, q: "taro", role: "admin", isActive: "false" });

		expect(client.get).toHaveBeenCalledWith("/admin/users", {
			params: { page: 2, per_page: 20, q: "taro", role: "admin", is_active: false },
		});
	});
});
