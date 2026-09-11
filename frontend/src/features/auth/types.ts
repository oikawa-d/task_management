/**
 * design doc: docs/detailed_design/screen/01_login.md §5、02_register.md §5
 * docs/basic_design/04_api.md §4.1（エラーレスポンス形式）と1対1で対応させる。
 */

/** ログインフォームの入力値（そのままAPIリクエストボディにもなる） */
export interface LoginFormValues {
	identifier: string;
	password: string;
}

/** メール認証再送APIへ送る内容 */
export interface ResendVerificationPayload {
	email: string;
}

/** 会員登録フォームの入力値（生年月日はプルダウン3つを保持する） */
export interface RegisterFormValues {
	last_name: string;
	first_name: string;
	last_name_kana: string;
	first_name_kana: string;
	birth_year: string;
	birth_month: string;
	birth_day: string;
	email: string;
	username: string;
	password: string;
	password_confirm: string;
}

/** POST /api/auth/register のリクエストボディ（birth_dateはYYYY-MM-DDへ整形済み） */
export type RegisterSubmitPayload = Omit<RegisterFormValues, "birth_year" | "birth_month" | "birth_day"> & {
	birth_date: string;
};

/** POST /api/auth/login のレスポンス（session: 204で本文なし / jwt: 200でaccess_token等） */
export interface LoginResponse {
	access_token?: string;
	token_type?: string;
	expires_in?: number;
}

/** POST /api/auth/register のレスポンス（201） */
export interface RegisterResponse {
	id: string;
	email: string;
	message: string;
}

/** 422 VALIDATION_ERROR の details 1件分 */
export interface ApiFieldError {
	field: string;
	message: string;
}

/** docs/basic_design/04_api.md §4.1 のエラーレスポンス形式に対応する送信元エラー */
export interface AuthApiError {
	status?: number;
	code?: string;
	message?: string;
	details?: ApiFieldError[] | null;
}

/** パスワード再設定要求フォームの入力値（docs/detailed_design/screen/03_password_forgot.md §5） */
export interface PasswordForgotFormValues {
	email: string;
}

/** パスワード再設定フォームの入力値（docs/detailed_design/screen/04_password_reset.md §5） */
export interface PasswordResetFormValues {
	newPassword: string;
	passwordConfirm: string;
}

/** メール認証再送フォームの入力値（docs/detailed_design/screen/05_verify_email.md §5） */
export interface ResendVerificationFormValues {
	email: string;
}
