import { createContext, type ReactNode } from "react";

/**
 * LoginPage/RegisterPageは、フォーム本体（LoginForm/RegisterForm/GoogleLoginButton）を
 * 直接importせず、スロットとして差し込む構造にする。
 * これにより、フォーム実装（#148）と認証状態実装（#149）を待たずにpage/routing（#147）を
 * 単独でビルド・テストできる。実際のフォームは、AuthFormsProviderのslotsに関数を渡すことで接続する
 * （frontend/src/features/settings/pages/SettingsPage.tsx の SettingsFormsProvider と同じ方式）。
 */

export type LoginFormSlotProps = {
	/** ログイン成功時に呼び出す。呼び出し元（LoginPage）が/dashboardへの遷移を行う */
	onSuccess: () => void;
};

export type RegisterFormSlotProps = {
	/** 登録成功時に呼び出す。呼び出し元（RegisterPage）が/loginへの遷移を行う */
	onSuccess: (email: string) => void;
};

export type GoogleLoginButtonSlotProps = {
	label: string;
};

export type LoginFormSlot = (props: LoginFormSlotProps) => ReactNode;
export type RegisterFormSlot = (props: RegisterFormSlotProps) => ReactNode;
export type GoogleLoginButtonSlot = (props: GoogleLoginButtonSlotProps) => ReactNode;

export type AuthFormSlots = {
	loginForm?: LoginFormSlot;
	registerForm?: RegisterFormSlot;
	googleLoginButton?: GoogleLoginButtonSlot;
};

export const AuthFormsContext = createContext<AuthFormSlots>({});

export function AuthFormsProvider({
	slots,
	children,
}: {
	slots?: AuthFormSlots;
	children: ReactNode;
}) {
	return <AuthFormsContext.Provider value={slots ?? {}}>{children}</AuthFormsContext.Provider>;
}

export function LoginFormPlaceholder({ onSuccess }: LoginFormSlotProps) {
	return (
		<form aria-label="ログインフォーム">
			<p>ログインフォームは今後実装予定です。</p>
			<button type="button" onClick={onSuccess}>
				ログイン
			</button>
		</form>
	);
}

export function RegisterFormPlaceholder({ onSuccess }: RegisterFormSlotProps) {
	return (
		<form aria-label="会員登録フォーム">
			<p>会員登録フォームは今後実装予定です。</p>
			<button type="button" onClick={() => onSuccess("")}>
				登録する
			</button>
		</form>
	);
}

export function GoogleLoginButtonPlaceholder({ label }: GoogleLoginButtonSlotProps) {
	return (
		<button type="button" disabled aria-label={`${label}（準備中）`}>
			{label}
		</button>
	);
}
