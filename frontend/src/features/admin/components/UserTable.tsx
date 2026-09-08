import type { AdminUserRole, AdminUserSummary } from "../types";
import UserRow from "./UserRow";

interface UserTableProps {
	users: AdminUserSummary[];
	currentUserId: string;
	onRoleChange: (userId: string, role: AdminUserRole) => Promise<void>;
	onStatusChange: (userId: string, isActive: boolean) => Promise<void>;
	onForceLogout: (userId: string) => Promise<void>;
	accessTokenTtlMinutes?: number;
}

function UserTable({
	users,
	currentUserId,
	onRoleChange,
	onStatusChange,
	onForceLogout,
	accessTokenTtlMinutes,
}: UserTableProps) {
	if (users.length === 0) {
		return <p>ユーザーが見つかりません</p>;
	}

	return (
		<table>
			<thead>
				<tr>
					<th>username</th>
					<th>email</th>
					<th>氏名</th>
					<th>role</th>
					<th>有効</th>
					<th>操作</th>
				</tr>
			</thead>
			<tbody>
				{users.map((user) => (
					<UserRow
						key={user.id}
						user={user}
						currentUserId={currentUserId}
						onRoleChange={onRoleChange}
						onStatusChange={onStatusChange}
						onForceLogout={onForceLogout}
						accessTokenTtlMinutes={accessTokenTtlMinutes}
					/>
				))}
			</tbody>
		</table>
	);
}

export default UserTable;
