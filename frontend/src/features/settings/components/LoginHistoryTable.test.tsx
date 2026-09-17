import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLoginHistory } from "../hooks/useLoginHistory";
import { LoginHistoryTable } from "./LoginHistoryTable";

vi.mock("../hooks/useLoginHistory", () => ({ useLoginHistory: vi.fn() }));

const mockedUseLoginHistory = vi.mocked(useLoginHistory);

describe("LoginHistoryTable", () => {
	beforeEach(() => vi.clearAllMocks());

	it.each([
		["読み込み中", { isLoading: true, isError: false, data: undefined }],
		["取得失敗", { isLoading: false, isError: true, data: undefined }],
		["空状態", { isLoading: false, isError: false, data: { items: [], meta: { count: 0, limit: 20 } } }],
	])("%s状態を共通でないstateスタイル付きで表示する", (_name, query) => {
		mockedUseLoginHistory.mockReturnValue({ ...query, refetch: vi.fn() } as never);
		render(<LoginHistoryTable />);
		expect(screen.getByRole(query.isError ? "alert" : "status").className).toContain("state");
	});

	it("履歴表示では共通AdminTableのwrapperとtableを利用する", () => {
		mockedUseLoginHistory.mockReturnValue({ isLoading: false, isError: false, data: { items: [{ id: "1", login_method: "session", ip_address: null, user_agent: null, success: true, failure_reason: null, created_at: "2026-09-10T00:00:00Z" }], meta: { count: 1, limit: 20 } }, refetch: vi.fn() } as never);
		render(<LoginHistoryTable />);
		expect(screen.getByRole("table").parentElement?.className).toContain("wrapper");
	});
});
