import type { AdminUserRole } from "../types";

interface RoleSelectProps {
	value: AdminUserRole;
	disabled?: boolean;
	disabledReason?: string;
	onChange: (role: AdminUserRole) => void;
}

function RoleSelect({ value, disabled = false, disabledReason, onChange }: RoleSelectProps) {
	return (
		<select
			aria-label="ロール"
			value={value}
			disabled={disabled}
			title={disabled ? disabledReason : undefined}
			onChange={(event) => onChange(event.target.value as AdminUserRole)}
		>
			<option value="member">member</option>
			<option value="admin">admin</option>
		</select>
	);
}

export default RoleSelect;
