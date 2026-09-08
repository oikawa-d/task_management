interface ForceLogoutButtonProps {
	onClick: () => void;
}

function ForceLogoutButton({ onClick }: ForceLogoutButtonProps) {
	return (
		<button type="button" onClick={onClick}>
			強制ログアウト
		</button>
	);
}

export default ForceLogoutButton;
