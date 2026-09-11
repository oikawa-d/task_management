import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UserTable } from "./UserTable";

const user = {
	id: "user-1",
	username: "taro",
	email: "taro@example.com",
	display_name: "山田 太郎",
	role: "admin" as const,
	is_active: true,
	created_at: "2026-09-01T00:00:00Z",
};

describe("UserTable", () => {
	it("現在ログイン中のユーザーは権限変更・状態変更だけを非活性にする", () => {
		render(<UserTable items={[user]} currentUserId={user.id} onRoleChange={vi.fn()} onStatusChange={vi.fn()} onForceLogout={vi.fn()} />);

		expect(screen.getByRole("combobox", { name: "山田 太郎の権限" })).toBeDisabled();
		expect(screen.getByRole("switch")).toBeDisabled();
		expect(screen.getByRole("button", { name: "強制ログアウト" })).toBeEnabled();
	});
});
