import { useState } from "react";
import { useForm } from "react-hook-form";

import { usePasswordReset } from "../hooks/usePasswordReset";
import type { PasswordResetFormValues } from "../types";
import { createZodResolver, getFieldErrors, passwordResetSchema } from "../validation";

/** APIのsnake_caseフィールド名 → RHFのcamelCaseフィールド名 */
const API_FIELD_TO_FORM_FIELD: Record<string, keyof PasswordResetFormValues> = {
	new_password: "newPassword",
	password_confirm: "passwordConfirm",
};

export interface PasswordResetFormProps {
	/** メール内リンクの#token=から抽出済みのトークン（呼び出し元がtoken欠落時は本コンポーネントを描画しない） */
	token: string;
	onSuccess?: () => void;
	/** トークンが無効・使用済み・期限切れ（400 INVALID_RESET_TOKEN）だった場合に呼ばれる */
	onTokenInvalid?: () => void;
}

/**
 * パスワード再設定フォーム。
 * docs/detailed_design/screen/04_password_reset.md
 */
export function PasswordResetForm({ token, onSuccess, onTokenInvalid }: PasswordResetFormProps) {
	const [tokenInvalid, setTokenInvalid] = useState(false);
	const [submitError, setSubmitError] = useState<string | null>(null);
	const mutation = usePasswordReset();
	const {
		register,
		handleSubmit,
		setError,
		formState: { errors, isSubmitting },
	} = useForm<PasswordResetFormValues>({
		defaultValues: { newPassword: "", passwordConfirm: "" },
		resolver: createZodResolver(passwordResetSchema()),
		mode: "onChange",
	});

	const submit = async (values: PasswordResetFormValues) => {
		setSubmitError(null);
		try {
			await mutation.mutateAsync({ token, newPassword: values.newPassword, passwordConfirm: values.passwordConfirm });
			onSuccess?.();
		} catch (error: unknown) {
			const code = typeof error === "object" && error && "code" in error ? (error as { code?: string }).code : undefined;
			if (code === "INVALID_RESET_TOKEN") {
				setTokenInvalid(true);
				onTokenInvalid?.();
				return;
			}
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				for (const fieldError of fieldErrors) {
					const formField = API_FIELD_TO_FORM_FIELD[fieldError.field];
					if (formField) {
						setError(formField, { type: "server", message: fieldError.message });
					}
				}
				return;
			}
			setSubmitError(toDisplayMessage(code, error));
		}
	};

	if (tokenInvalid) {
		return <p role="alert">リンクの有効期限が切れているか、既に使用済みです</p>;
	}

	return (
		<form onSubmit={handleSubmit(submit)} noValidate>
			<label htmlFor="password-reset-new-password">新しいパスワード</label>
			<input
				id="password-reset-new-password"
				type="password"
				aria-invalid={Boolean(errors.newPassword)}
				aria-describedby={errors.newPassword ? "password-reset-new-password-error" : undefined}
				{...register("newPassword")}
			/>
			{errors.newPassword && (
				<span id="password-reset-new-password-error" role="alert">
					{errors.newPassword.message}
				</span>
			)}

			<label htmlFor="password-reset-confirm">新しいパスワード（確認）</label>
			<input
				id="password-reset-confirm"
				type="password"
				aria-invalid={Boolean(errors.passwordConfirm)}
				aria-describedby={errors.passwordConfirm ? "password-reset-confirm-error" : undefined}
				{...register("passwordConfirm")}
			/>
			{errors.passwordConfirm && (
				<span id="password-reset-confirm-error" role="alert">
					{errors.passwordConfirm.message}
				</span>
			)}

			{submitError && <p role="alert">{submitError}</p>}

			<button type="submit" disabled={isSubmitting}>
				{isSubmitting ? "送信中…" : "再設定する"}
			</button>
		</form>
	);
}

function toDisplayMessage(code: string | undefined, error: unknown): string {
	if (code === "TOO_MANY_ATTEMPTS") {
		const retryAfterSeconds = typeof error === "object" && error && "retryAfterSeconds" in error
			? (error as { retryAfterSeconds?: number | null }).retryAfterSeconds
			: null;
		return retryAfterSeconds
			? `送信回数の上限に達しました。${retryAfterSeconds}秒後に再度お試しください`
			: "送信回数の上限に達しました。しばらくしてから再度お試しください";
	}
	if (code === "SERVICE_UNAVAILABLE") {
		return "サービスが一時的に利用できません。しばらくしてから再度お試しください";
	}
	return "パスワードの再設定に失敗しました。しばらくしてから再度お試しください";
}
