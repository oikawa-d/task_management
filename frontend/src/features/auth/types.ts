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
