/**
 * メール認証・パスワードリセット関連のフォーム値・API入出力型。
 * 参照: docs/detailed_design/screen/03_password_forgot.md〜05_verify_email.md
 */

export interface PasswordForgotFormValues {
	email: string;
}

export interface PasswordResetFormValues {
	newPassword: string;
	passwordConfirm: string;
}

export interface ResendVerificationFormValues {
	email: string;
}

/** 422 VALIDATION_ERRORのdetails配列1件分（basic_design/04_api.md §4.1） */
export interface ApiFieldError {
	field: string;
	message: string;
}
