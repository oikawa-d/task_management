import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AdminUserSummary } from "../types";
import UserRow from "./UserRow";

const CURRENT_USER_ID = "user-1";

function buildUser(overrides: Partial<AdminUserSummary> = {}): AdminUserSummary {
	return {
		id: "user-2",
		username: "hanako",
		email: "hanako@example.com",
		displayName: "花子",
		role: "member",
		isActive: true,
		...overrides,
	};
}

function renderRow(overrides: Partial<AdminUserSummary> = {}) {
	const onRoleChange = vi.fn().mockResolvedValue(undefined);
	const onStatusChange = vi.fn().mockResolvedValue(undefined);
	const onForceLogout = vi.fn().mockResolvedValue(undefined);

	render(
		<table>
			<tbody>
				<UserRow
					user={buildUser(overrides)}
					currentUserId={CURRENT_USER_ID}
					onRoleChange={onRoleChange}
					onStatusChange={onStatusChange}
					onForceLogout={onForceLogout}
				/>
			</tbody>
		</table>,
	);

	return { onRoleChange, onStatusChange, onForceLogout };
}

describe("UserRow", () => {
	it("disables role select and status toggle for self but keeps force logout enabled", () => {
		renderRow({ id: CURRENT_USER_ID });

		const roleSelect = screen.getByRole("combobox", { name: "ロール" });
		const statusToggle = screen.getByRole("switch", { name: "有効/無効" });
		const forceLogoutButton = screen.getByRole("button", { name: "強制ログアウト" });

		expect(roleSelect).toBeDisabled();
		expect(roleSelect).toHaveAttribute("title", "自分自身は変更できません");
		expect(statusToggle).toBeDisabled();
		expect(statusToggle).toHaveAttribute("title", "自分自身は変更できません");
		expect(forceLogoutButton).not.toBeDisabled();
	});

	it("calls onRoleChange after confirming a role change and closes the dialog on success", async () => {
		const { onRoleChange } = renderRow({ role: "member" });

		fireEvent.change(screen.getByRole("combobox", { name: "ロール" }), {
			target: { value: "admin" },
		});

		expect(screen.getByRole("alertdialog")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "確定" }));

		await waitFor(() => {
			expect(onRoleChange).toHaveBeenCalledWith("user-2", "admin");
		});
		await waitFor(() => {
			expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
		});
	});

	it("keeps the dialog open and shows the error message when onRoleChange rejects", async () => {
		const onRoleChange = vi.fn().mockRejectedValue(new Error("最後の管理者を降格することはできません"));
		const onStatusChange = vi.fn().mockResolvedValue(undefined);
		const onForceLogout = vi.fn().mockResolvedValue(undefined);

		render(
			<table>
				<tbody>
					<UserRow
						user={buildUser({ role: "admin" })}
						currentUserId={CURRENT_USER_ID}
						onRoleChange={onRoleChange}
						onStatusChange={onStatusChange}
						onForceLogout={onForceLogout}
					/>
				</tbody>
			</table>,
		);

		fireEvent.change(screen.getByRole("combobox", { name: "ロール" }), {
			target: { value: "member" },
		});
		fireEvent.click(screen.getByRole("button", { name: "確定" }));

		await waitFor(() => {
			expect(screen.getByText("最後の管理者を降格することはできません")).toBeInTheDocument();
		});
		expect(screen.getByRole("alertdialog")).toBeInTheDocument();
	});

	it("requires confirmation before deactivating a user", async () => {
		const { onStatusChange } = renderRow({ isActive: true });

		fireEvent.click(screen.getByRole("switch", { name: "有効/無効" }));

		expect(screen.getByRole("alertdialog")).toBeInTheDocument();
		expect(onStatusChange).not.toHaveBeenCalled();

		fireEvent.click(screen.getByRole("button", { name: "確定" }));

		await waitFor(() => {
			expect(onStatusChange).toHaveBeenCalledWith("user-2", false);
		});
	});

	it("reactivates without a confirmation dialog", async () => {
		const { onStatusChange } = renderRow({ isActive: false });

		fireEvent.click(screen.getByRole("switch", { name: "有効/無効" }));

		expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
		await waitFor(() => {
			expect(onStatusChange).toHaveBeenCalledWith("user-2", true);
		});
	});

	it("calls onForceLogout after confirming the force logout dialog", async () => {
		const { onForceLogout } = renderRow();

		fireEvent.click(screen.getByRole("button", { name: "強制ログアウト" }));

		expect(screen.getByRole("alertdialog")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "確定" }));

		await waitFor(() => {
			expect(onForceLogout).toHaveBeenCalledWith("user-2");
		});
	});
});
