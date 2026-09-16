import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { usePasswordForgot } from "../hooks/usePasswordForgot";
import type { PasswordForgotFormValues } from "../types";
import { createZodResolver, getFieldErrors, passwordForgotSchema } from "../validation";

type FormState = "idle" | "submitting" | "sent" | "error";

export interface PasswordForgotFormProps {
	/** 送信成功（202受信）時に呼ばれる。フォームは自身でも完了メッセージへ切り替わる */
	onSent?: () => void;
}

/**
 * パスワード再設定要求フォーム。
 * docs/detailed_design/screen/03_password_forgot.md
 */
export function PasswordForgotForm({ onSent }: PasswordForgotFormProps) {
	const [formState, setFormState] = useState<FormState>("idle");
	const [lastError, setLastError] = useState<{ code?: string; message: string } | null>(null);
	const sentHeadingRef = useRef<HTMLHeadingElement>(null);
	const mutation = usePasswordForgot();
	const {
		register,
		handleSubmit,
		setError,
		watch,
		formState: { errors },
	} = useForm<PasswordForgotFormValues>({
		defaultValues: { email: "" },
		resolver: createZodResolver(passwordForgotSchema),
		mode: "onChange",
	});
	const email = watch("email");

	useEffect(() => {
		if (formState === "sent") {
			sentHeadingRef.current?.focus();
		}
	}, [formState]);

	const submit = async (values: PasswordForgotFormValues) => {
		setFormState("submitting");
		setLastError(null);
		try {
			await mutation.mutateAsync(values);
			setFormState("sent");
			onSent?.();
		} catch (error: unknown) {
			setFormState("error");
			const fieldErrors = getFieldErrors(error);
			const emailError = fieldErrors.find((fieldError) => fieldError.field === "email");
			if (emailError) {
				setError("email", { type: "server", message: emailError.message });
			} else {
				setLastError(toDisplayError(error));
			}
		}
	};

	if (formState === "sent") {
		return (
			<h2 tabIndex={-1} ref={sentHeadingRef} role="status" aria-live="polite">
				ご入力のメールアドレスが登録されている場合、パスワード再設定用のメールを送信しました。
			</h2>
		);
	}

	return (
		<form onSubmit={handleSubmit(submit)} noValidate>
			<label htmlFor="password-forgot-email">メールアドレス</label>
			<input
				id="password-forgot-email"
				type="email"
				autoFocus
				aria-required="true"
				aria-invalid={Boolean(errors.email)}
				aria-describedby={errors.email ? "password-forgot-email-error" : undefined}
				{...register("email")}
			/>
			{errors.email && (
				<span id="password-forgot-email-error" role="alert">
					{errors.email.message}
				</span>
			)}
			{lastError && <p role="alert">{lastError.message}</p>}
			<button type="submit" disabled={formState === "submitting" || Boolean(errors.email) || !email}>
				{formState === "submitting" ? "送信中…" : "送信"}
			</button>
		</form>
	);
}

function toDisplayError(error: unknown): { code?: string; message: string } {
	const code = typeof error === "object" && error && "code" in error ? (error as { code?: string }).code : undefined;
	if (code === "TOO_MANY_ATTEMPTS") {
		const retryAfterSeconds = typeof error === "object" && error && "retryAfterSeconds" in error
			? (error as { retryAfterSeconds?: number | null }).retryAfterSeconds
			: null;
		return {
			code,
			message: retryAfterSeconds
				? `送信回数の上限に達しました。${retryAfterSeconds}秒後に再度お試しください`
				: "送信回数の上限に達しました。しばらくしてから再度お試しください",
		};
	}
	if (code === "VALIDATION_ERROR") {
		return { code, message: "メールアドレスの形式が正しくありません" };
	}
	return { code, message: "エラーが発生しました。しばらくしてから再度お試しください" };
}
