import { afterEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter } from "../../api/authAdapter/client";
import { getProjectTasks } from "./api";

describe("board API", () => {
	afterEach(() => {
		clearAuthAdapter();
		vi.unstubAllGlobals();
	});

	it("共通認証クライアント経由でボードを取得する", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ auth_mode: "session" }),
			})
			.mockResolvedValueOnce({
				ok: true,
				status: 200,
				json: () => Promise.resolve({ columns: { todo: [], in_progress: [], done: [] } }),
			});
		vi.stubGlobal("fetch", fetchMock);

		await expect(getProjectTasks("project-1")).resolves.toEqual({
			columns: { todo: [], in_progress: [], done: [] },
		});

		expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/project-1/tasks", expect.any(Object));
	});
});
