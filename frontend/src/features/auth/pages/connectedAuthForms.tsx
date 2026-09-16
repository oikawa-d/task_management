import { GoogleLoginButton } from "../components/GoogleLoginButton";
import { LoginForm } from "../components/LoginForm";
import { RegisterForm } from "../components/RegisterForm";
import { useLogin } from "../hooks/useLogin";
import { useRegister } from "../hooks/useRegister";
import { useResendVerification } from "../hooks/useResendVerification";
import type {
	AuthFormSlots,
	GoogleLoginButtonSlotProps,
	LoginFormSlotProps,
	RegisterFormSlotProps,
} from "./authFormSlots";

/**
 * issue #315: authFormSlots.tsxのスロット（#147）へ、フォーム本体（#148）と
 * API呼び出し・authStore更新（既存の frontend/src/auth/ ・ frontend/src/api/authAdapter/ 経由、#149）を結線する。
 * design doc: docs/detailed_design/screen/01_login.md、02_register.md
 */
function ConnectedLoginForm({ onSuccess }: LoginFormSlotProps) {
	const loginMutation = useLogin();
	const resendMutation = useResendVerification();

	return (
		<LoginForm
			onSubmit={async (values) => {
				await loginMutation.mutateAsync(values);
				onSuccess();
			}}
			onResendVerification={(payload) => resendMutation.mutateAsync(payload)}
		/>
	);
}

function ConnectedRegisterForm({ onSuccess }: RegisterFormSlotProps) {
	const registerMutation = useRegister();

	return (
		<RegisterForm
			onSubmit={async (payload) => {
				await registerMutation.mutateAsync(payload);
			}}
			onSuccess={onSuccess}
		/>
	);
}

/**
 * LoginPage/RegisterPageが既にauthStore.googleLoginEnabledで呼び出し可否を判定しているため
 * （呼ばれた時点でtrue確定）、ここでは常時enabledでGoogleLoginButtonを描画する。
 */
function ConnectedGoogleLoginButton({ label }: GoogleLoginButtonSlotProps) {
	return <GoogleLoginButton enabled label={label} />;
}

/** main.tsxでAppへ渡し、AuthFormsProviderのslotsへ注入する */
export const authFormSlots: AuthFormSlots = {
	loginForm: (props) => <ConnectedLoginForm {...props} />,
	registerForm: (props) => <ConnectedRegisterForm {...props} />,
	googleLoginButton: (props) => <ConnectedGoogleLoginButton {...props} />,
};
