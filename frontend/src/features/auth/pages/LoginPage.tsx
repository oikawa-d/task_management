import { useContext, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../../auth/authStore";
import { consumeLoginMessage } from "../../../auth/loginMessage";
import { ROUTES } from "../../../routes";
import { AuthFormsContext, LoginFormPlaceholder } from "./authFormSlots";

type LoginLocationState = {
	registeredEmail?: string;
	message?: string;
};

function RegisteredMessage({ email }: { email?: string }) {
	if (!email) {
		return null;
	}

	return <p role="status">確認メールを送信しました（{email}）</p>;
}

function LoginMessage({ message }: { message?: string }) {
	if (!message) {
		return null;
	}

	return <p role="status">{message}</p>;
}

export function LoginPage() {
	const navigate = useNavigate();
	const location = useLocation();
	const formSlots = useContext(AuthFormsContext);
	const googleLoginEnabled = useAuthStore((state) => state.googleLoginEnabled);
	const loginState = location.state as LoginLocationState | null;
	const registeredEmail = loginState?.registeredEmail;
	const [storedMessage, setStoredMessage] = useState<string | null>(null);

	useEffect(() => {
		setStoredMessage(consumeLoginMessage());
	}, []);

	const handleLoginSuccess = () => {
		navigate(ROUTES.DASHBOARD, { replace: true });
	};

	const loginForm = formSlots.loginForm
		? formSlots.loginForm({ onSuccess: handleLoginSuccess })
		: <LoginFormPlaceholder onSuccess={handleLoginSuccess} />;

	// design doc: docs/detailed_design/screen/01_login.md §3⑦
	// authStore.googleLoginEnabled（AuthProvider起動時にGET /auth/configから設定）がtrue、
	// かつスロット接続済みの場合のみ「または」区切りとGoogleログイン導線を表示する。
	const googleLoginButton =
		formSlots.googleLoginButton && googleLoginEnabled
			? formSlots.googleLoginButton({ label: "Googleでログイン" })
			: null;

	return (
		<section aria-labelledby="login-heading">
			<h1 id="login-heading">Cerberus</h1>
			<LoginMessage message={loginState?.message ?? storedMessage ?? undefined} />
			<RegisteredMessage email={registeredEmail} />
			{loginForm}
			{googleLoginButton ? (
				<>
					<p aria-hidden="true">または</p>
					{googleLoginButton}
				</>
			) : null}
			<p>
				<Link to={ROUTES.REGISTER}>新規会員登録はこちら</Link>
			</p>
			<p>
				<Link to={ROUTES.PASSWORD_FORGOT}>パスワードを忘れた方はこちら</Link>
			</p>
		</section>
	);
}
