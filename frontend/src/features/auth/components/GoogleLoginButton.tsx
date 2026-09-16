import styles from "./GoogleLoginButton.module.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export interface GoogleLoginButtonProps {
	enabled: boolean;
	label?: string;
}

/**
 * design doc: docs/detailed_design/screen/01_login.md §3⑦、02_register.md §3⑯
 * `window.location.href` によるフルページ遷移でOAuth開始APIへ送るため、jsdomでの実遷移検証はできない
 * （画面設計書§14「網羅できない範囲」）。遷移先URLの組み立てのみ単体で検証する。
 */
export function GoogleLoginButton({ enabled, label = "Googleでログイン" }: GoogleLoginButtonProps) {
	if (!enabled) {
		return null;
	}

	return (
		<button
			className={styles.button}
			type="button"
			onClick={() => {
				window.location.href = buildGoogleOAuthUrl();
			}}
		>
			{label}
		</button>
	);
}

export function buildGoogleOAuthUrl(): string {
	return `${API_BASE_URL}/auth/oauth/google`;
}
