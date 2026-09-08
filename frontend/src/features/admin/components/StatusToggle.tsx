interface StatusToggleProps {
	checked: boolean;
	disabled?: boolean;
	disabledReason?: string;
	onToggle: (nextChecked: boolean) => void;
}

function StatusToggle({ checked, disabled = false, disabledReason, onToggle }: StatusToggleProps) {
	return (
		<button
			type="button"
			role="switch"
			aria-checked={checked}
			aria-label="有効/無効"
			disabled={disabled}
			title={disabled ? disabledReason : undefined}
			onClick={() => onToggle(!checked)}
		>
			{checked ? "有効" : "無効"}
		</button>
	);
}

export default StatusToggle;
