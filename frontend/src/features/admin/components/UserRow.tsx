import { useState } from "react";
import { createPortal } from "react-dom";

import { ACCESS_TOKEN_TTL_MINUTES } from "../config";
import type { AdminUserRole, AdminUserSummary } from "../types";
import ConfirmDialog from "./ConfirmDialog";
import ForceLogoutButton from "./ForceLogoutButton";
import RoleSelect from "./RoleSelect";
import StatusToggle from "./StatusToggle";

export function isSelf(targetUserId: string, currentUserId: string): boolean {
	return targetUserId === currentUserId;
}

const SELF_DISABLED_REASON = "自分自身は変更できません";

type PendingAction =
	| { type: "role"; role: AdminUserRole }
	| { type: "status"; isActive: boolean }
	| { type: "forceLogout" };

interface UserRowProps {
	user: AdminUserSummary;
	currentUserId: string;
	onRoleChange: (userId: string, role: AdminUserRole) => Promise<void>;
	onStatusChange: (userId: string, isActive: boolean) => Promise<void>;
	onForceLogout: (userId: string) => Promise<void>;
	accessTokenTtlMinutes?: number;
}

function UserRow({
	user,
	currentUserId,
	onRoleChange,
	onStatusChange,
	onForceLogout,
	accessTokenTtlMinutes = ACCESS_TOKEN_TTL_MINUTES,
}: UserRowProps) {
	const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);

	const self = isSelf(user.id, currentUserId);

	const closeDialog = () => {
		setPendingAction(null);
		setErrorMessage(null);
		setIsSubmitting(false);
	};

	const handleRoleSelectChange = (role: AdminUserRole) => {
		setErrorMessage(null);
		setPendingAction({ type: "role", role });
	};

	const handleStatusToggle = (nextIsActive: boolean) => {
		if (!nextIsActive) {
			setErrorMessage(null);
			setPendingAction({ type: "status", isActive: false });
			return;
		}
		void onStatusChange(user.id, true);
	};

	const handleForceLogoutClick = () => {
		setErrorMessage(null);
		setPendingAction({ type: "forceLogout" });
	};

	const handleConfirm = async () => {
		if (!pendingAction) {
			return;
		}
		setIsSubmitting(true);
		setErrorMessage(null);
		try {
			if (pendingAction.type === "role") {
				await onRoleChange(user.id, pendingAction.role);
			} else if (pendingAction.type === "status") {
				await onStatusChange(user.id, pendingAction.isActive);
			} else {
				await onForceLogout(user.id);
			}
			closeDialog();
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			setErrorMessage(message);
			setIsSubmitting(false);
		}
	};

	const dialogContent = getDialogContent(pendingAction, accessTokenTtlMinutes);

	return (
		<>
			<tr>
				<td>{user.username}</td>
				<td>{user.email}</td>
				<td>{user.displayName}</td>
				<td>
					<RoleSelect
						value={user.role}
						disabled={self}
						disabledReason={self ? SELF_DISABLED_REASON : undefined}
						onChange={handleRoleSelectChange}
					/>
				</td>
				<td>
					<StatusToggle
						checked={user.isActive}
						disabled={self}
						disabledReason={self ? SELF_DISABLED_REASON : undefined}
						onToggle={handleStatusToggle}
					/>
				</td>
				<td>
					<ForceLogoutButton onClick={handleForceLogoutClick} />
				</td>
			</tr>
			{dialogContent
				? createPortal(
						<ConfirmDialog
							open
							title={dialogContent.title}
							message={dialogContent.message}
							confirmLabel="確定"
							cancelLabel="キャンセル"
							errorMessage={errorMessage}
							isSubmitting={isSubmitting}
							onConfirm={() => void handleConfirm()}
							onCancel={closeDialog}
						/>,
						document.body,
					)
				: null}
		</>
	);
}

function getDialogContent(
	pendingAction: PendingAction | null,
	accessTokenTtlMinutes: number,
): { title: string; message: string } | null {
	if (!pendingAction) {
		return null;
	}
	if (pendingAction.type === "role") {
		return {
			title: "ロール変更の確認",
			message: `ロールを${pendingAction.role}に変更しますか？`,
		};
	}
	if (pendingAction.type === "status") {
		return {
			title: "無効化の確認",
			message: "無効化すると全セッションが即時失効します。よろしいですか？",
		};
	}
	return {
		title: "強制ログアウトの確認",
		message: `強制ログアウトを実行します。session/refreshは即時失効しますが、access tokenは最大${accessTokenTtlMinutes}分残ります。`,
	};
}

export default UserRow;
