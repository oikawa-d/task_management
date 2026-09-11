import { useContext } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { AuthFormsContext, RegisterFormPlaceholder } from "./authFormSlots";

export function RegisterPage() {
	const navigate = useNavigate();
	const formSlots = useContext(AuthFormsContext);
	const googleLoginEnabled = useAuthStore((state) => state.googleLoginEnabled);

	const handleRegisterSuccess = (email: string) => {
		navigate(ROUTES.LOGIN, { state: { registeredEmail: email } });
	};

	const registerForm = formSlots.registerForm
		? formSlots.registerForm({ onSuccess: handleRegisterSuccess })
		: <RegisterFormPlaceholder onSuccess={handleRegisterSuccess} />;

	// design doc: docs/detailed_design/screen/02_register.md §3⑯
	// authStore.googleLoginEnabled（AuthProvider起動時にGET /auth/configから設定）がtrue、
	// かつスロット接続済みの場合のみ「または」区切りとGoogleログイン導線を表示する。
	const googleLoginButton =
		formSlots.googleLoginButton && googleLoginEnabled
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
