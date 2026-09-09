import { useContext } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ROUTES } from "../../../routes";
import { AuthFormsContext, RegisterFormPlaceholder } from "./authFormSlots";

export function RegisterPage() {
	const navigate = useNavigate();
	const formSlots = useContext(AuthFormsContext);

	const handleRegisterSuccess = (email: string) => {
		navigate(ROUTES.LOGIN, { state: { registeredEmail: email } });
	};

	const registerForm = formSlots.registerForm
		? formSlots.registerForm({ onSuccess: handleRegisterSuccess })
		: <RegisterFormPlaceholder onSuccess={handleRegisterSuccess} />;

	// GoogleでログインはauthConfig.google_login_enabledがtrueの場合のみ表示する（#149の認証状態実装と接続予定）。
	// スロットが未接続の間は非表示とする。
	const googleLoginButton = formSlots.googleLoginButton
		? formSlots.googleLoginButton({ label: "Googleで新規登録" })
		: null;

	return (
		<section aria-labelledby="register-heading">
			<h1 id="register-heading">Cerberus 会員登録</h1>
			{registerForm}
			{googleLoginButton ? (
				<>
					<p aria-hidden="true">または</p>
					{googleLoginButton}
				</>
			) : null}
			<p>
				<Link to={ROUTES.LOGIN}>既にアカウントをお持ちの方はこちら</Link>
			</p>
		</section>
	);
}
