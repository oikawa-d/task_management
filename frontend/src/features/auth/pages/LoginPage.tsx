import { useContext } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ROUTES } from "../../../routes";
import { AuthFormsContext, LoginFormPlaceholder } from "./authFormSlots";

type LoginLocationState = {
	registeredEmail?: string;
};

function RegisteredMessage({ email }: { email?: string }) {
	if (!email) {
		return null;
	}

	return <p role="status">確認メールを送信しました（{email}）</p>;
}

export function LoginPage() {
	const navigate = useNavigate();
	const location = useLocation();
	const formSlots = useContext(AuthFormsContext);
	const registeredEmail = (location.state as LoginLocationState | null)?.registeredEmail;

	const handleLoginSuccess = () => {
		navigate(ROUTES.DASHBOARD, { replace: true });
	};

	const loginForm = formSlots.loginForm
		? formSlots.loginForm({ onSuccess: handleLoginSuccess })
		: <LoginFormPlaceholder onSuccess={handleLoginSuccess} />;

	// GoogleログインはauthConfig.google_login_enabledがtrueの場合のみ表示する（#149の認証状態実装と接続予定）。
	// スロットが未接続の間は非表示とする。
	const googleLoginButton = formSlots.googleLoginButton
		? formSlots.googleLoginButton({ label: "Googleでログイン" })
		: null;

	return (
		<section aria-labelledby="login-heading">
			<h1 id="login-heading">Cerberus</h1>
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
