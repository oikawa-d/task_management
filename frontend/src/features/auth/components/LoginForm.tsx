import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import type { LoginFormValues } from "../types";
import { buildResendPayload, createZodResolver, getErrorCode, getFieldErrors, loginSchema } from "../validation";
import { PasswordField } from "./PasswordField";
import styles from "./LoginForm.module.css";

const ERROR_MESSAGES: Record<string, string> = {
	INVALID_CREDENTIALS: "IDまたはパスワードが正しくありません",
	USER_INACTIVE: "アカウントが無効化されています。管理者にお問い合わせください",
	TOO_MANY_ATTEMPTS: "試行回数が多いため、しばらく待ってから再度お試しください",
};
const GENERIC_ERROR_MESSAGE = "エラーが発生しました。しばらくしてから再度お試しください";
const NETWORK_ERROR_MESSAGE = "通信に失敗しました";

export interface LoginFormProps {
	onSubmit: (values: LoginFormValues) => Promise<void>;
	onResendVerification: (payload: { email: string }) => Promise<void>;
}

type ResendState = "idle" | "sending" | "sent";

export function LoginForm({ onSubmit, onResendVerification }: LoginFormProps) {
	const [lastError, setLastError] = useState<{ code?: string; message: string } | null>(null);
	const [showPassword, setShowPassword] = useState(false);
	const [resendState, setResendState] = useState<ResendState>("idle");
	const [resendEmail, setResendEmail] = useState("");
	const identifierRef = useRef<HTMLInputElement | null>(null);
	const {
		register,
		handleSubmit,
		getValues,
		watch,
		setError,
		formState: { errors, isSubmitting },
	} = useForm<LoginFormValues>({
		defaultValues: { identifier: "", password: "" },
		resolver: createZodResolver(loginSchema),
		mode: "onChange",
	});

	useEffect(() => {
		identifierRef.current?.focus();
	}, []);

	const submit = async (values: LoginFormValues) => {
		setLastError(null);
		setResendState("idle");
		try {
			await onSubmit(values);
		} catch (error: unknown) {
			const code = getErrorCode(error);
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				for (const fieldError of fieldErrors) {
					if (fieldError.field === "identifier" || fieldError.field === "password") {
						setError(fieldError.field, { type: "server", message: fieldError.message });
					}
				}
				return;
			}
			setLastError({ code, message: resolveErrorMessage(code, error) });
		}
	};

	const handleResend = async () => {
		const email = buildResendPayload(getValues("identifier")) ?? (resendEmail ? { email: resendEmail } : null);
		if (!email) {
			return;
		}
		setResendState("sending");
		await onResendVerification(email);
		setResendState("sent");
	};

	const identifierRegistration = register("identifier");
	const identifierValue = watch("identifier");
	const isEmailIdentifier = buildResendPayload(identifierValue) !== null;

	return (
		<form className={styles.form} onSubmit={handleSubmit(submit)} noValidate>
			<div className={styles.field}>
				<label htmlFor="identifier">IDもしくはメールアドレス</label>
				<input
					id="identifier"
					className={styles.input}
					{...identifierRegistration}
					ref={(element) => {
						identifierRegistration.ref(element);
						identifierRef.current = element;
					}}
					aria-required="true"
					aria-invalid={Boolean(errors.identifier)}
					aria-describedby={errors.identifier ? "identifier-error" : undefined}
				/>
				{errors.identifier && <span className={styles.error} id="identifier-error">{errors.identifier.message}</span>}
			</div>

			<PasswordField
				name="password"
				label="パスワード"
				registration={register("password")}
				error={errors.password?.message}
				isVisible={showPassword}
				onToggle={() => setShowPassword((current) => !current)}
			/>

			{lastError?.code === "EMAIL_NOT_VERIFIED" && (
				<div className={styles.banner} role="alert" aria-live="assertive">
					<p>メール認証が完了していません</p>
					{!isEmailIdentifier && (
						<input
							className={styles.input}
							type="email"
							aria-label="再送先メールアドレス"
							value={resendEmail}
							onChange={(event) => setResendEmail(event.target.value)}
						/>
					)}
					<button type="button" onClick={handleResend} disabled={resendState === "sending"}>
						{resendState === "sent" ? "送信しました" : "認証メールを再送する"}
					</button>
				</div>
			)}

			{lastError && lastError.code !== "EMAIL_NOT_VERIFIED" && (
				<p className={styles.error} role="alert" aria-live="assertive">{lastError.message}</p>
			)}

			<button className={styles.button} type="submit" disabled={isSubmitting}>
				{isSubmitting ? "ログイン中…" : "ログイン"}
			</button>
		</form>
	);
}

function resolveErrorMessage(code: string | undefined, error: unknown): string {
	if (!code) {
		return isNetworkError(error) ? NETWORK_ERROR_MESSAGE : GENERIC_ERROR_MESSAGE;
	}
	return ERROR_MESSAGES[code] ?? GENERIC_ERROR_MESSAGE;
}

function isNetworkError(error: unknown): boolean {
	return error instanceof TypeError || (error !== null && typeof error === "object" && !("status" in error) && !("code" in error));
}
