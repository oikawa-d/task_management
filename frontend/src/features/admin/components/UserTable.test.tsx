import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AdminUserSummary } from "../types";
import UserTable from "./UserTable";

const CURRENT_USER_ID = "user-1";

function buildUsers(): AdminUserSummary[] {
	return [
		{
			id: "user-1",
			username: "taro",
			email: "taro@example.com",
			displayName: "太郎",
			role: "admin",
			isActive: true,
		},
		{
			id: "user-2",
			username: "hanako",
			email: "hanako@example.com",
			displayName: "花子",
			role: "member",
			isActive: true,
		},
	];
}

describe("UserTable", () => {
	it("renders one row per user", () => {
		render(
			<UserTable
				users={buildUsers()}
				currentUserId={CURRENT_USER_ID}
				onRoleChange={vi.fn().mockResolvedValue(undefined)}
				onStatusChange={vi.fn().mockResolvedValue(undefined)}
				onForceLogout={vi.fn().mockResolvedValue(undefined)}
			/>,
		);

		expect(screen.getByText("taro")).toBeInTheDocument();
		expect(screen.getByText("hanako")).toBeInTheDocument();
		expect(screen.getAllByRole("row")).toHaveLength(3);
	});

	it("shows an empty state message when there are no users", () => {
		render(
			<UserTable
				users={[]}
				currentUserId={CURRENT_USER_ID}
				onRoleChange={vi.fn().mockResolvedValue(undefined)}
				onStatusChange={vi.fn().mockResolvedValue(undefined)}
				onForceLogout={vi.fn().mockResolvedValue(undefined)}
			/>,
		);

		expect(screen.getByText("ユーザーが見つかりません")).toBeInTheDocument();
	});
});
