import { useState } from "react";
import { useForm } from "react-hook-form";

import type { RegisterFormValues, RegisterSubmitPayload } from "../types";
import { createZodResolver, getErrorCode, getFieldErrors, registerSchema } from "../validation";
import { BirthDateSelect } from "./BirthDateSelect";
import { PasswordField } from "./PasswordField";
import { PasswordStrengthMeter } from "./PasswordStrengthMeter";
import styles from "./RegisterForm.module.css";

const DUPLICATE_CODE_TO_FIELD: Record<string, keyof RegisterFormValues> = {
	DUPLICATE_USERNAME: "username",
	DUPLICATE_EMAIL: "email",
};
const DUPLICATE_MESSAGES: Record<string, string> = {
	DUPLICATE_USERNAME: "このユーザー名は既に使用されています",
	DUPLICATE_EMAIL: "このメールアドレスは既に登録されています",
};
const GENERIC_ERROR_MESSAGE = "登録に失敗しました。しばらくしてから再度お試しください";
const NETWORK_ERROR_MESSAGE = "通信に失敗しました";

const DEFAULT_VALUES: RegisterFormValues = {
	last_name: "",
	first_name: "",
	last_name_kana: "",
	first_name_kana: "",
	birth_year: "",
	birth_month: "",
	birth_day: "",
	email: "",
	username: "",
	password: "",
	password_confirm: "",
};

export interface RegisterFormProps {
	onSubmit: (payload: RegisterSubmitPayload) => Promise<void>;
	onSuccess?: (email: string) => void;
}

export function RegisterForm({ onSubmit, onSuccess }: RegisterFormProps) {
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [showPassword, setShowPassword] = useState(false);
	const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
	const {
		register,
		handleSubmit,
		setError,
		watch,
		setValue,
		formState: { errors, isSubmitting },
	} = useForm<RegisterFormValues>({
		defaultValues: DEFAULT_VALUES,
		resolver: createZodResolver(registerSchema()),
		mode: "onChange",
	});

	const submit = async (values: RegisterFormValues) => {
		setSubmitError(null);
		try {
			await onSubmit(toSubmitPayload(values));
			onSuccess?.(values.email);
		} catch (error: unknown) {
			const code = getErrorCode(error);
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				for (const fieldError of fieldErrors) {
					if (fieldError.field in DEFAULT_VALUES) {
						setError(fieldError.field as keyof RegisterFormValues, { type: "server", message: fieldError.message });
					}
				}
				return;
			}
			if (code && code in DUPLICATE_CODE_TO_FIELD) {
				setError(DUPLICATE_CODE_TO_FIELD[code], { type: "server", message: DUPLICATE_MESSAGES[code] });
				return;
			}
			setSubmitError(isNetworkError(error) ? NETWORK_ERROR_MESSAGE : GENERIC_ERROR_MESSAGE);
		}
	};

	const password = watch("password");
	const birthYear = watch("birth_year");
	const birthMonth = watch("birth_month");
	const birthDay = watch("birth_day");

	return (
		<form className={styles.form} onSubmit={handleSubmit(submit)} noValidate>
			<div className={styles.row}>
				<TextField name="last_name" label="姓" registration={register("last_name")} error={errors.last_name?.message} />
				<TextField name="first_name" label="名" registration={register("first_name")} error={errors.first_name?.message} />
			</div>
			<div className={styles.row}>
				<TextField name="last_name_kana" label="セイ" registration={register("last_name_kana")} error={errors.last_name_kana?.message} />
				<TextField name="first_name_kana" label="メイ" registration={register("first_name_kana")} error={errors.first_name_kana?.message} />
			</div>

			<div className={styles.field}>
				<span>生年月日</span>
				<BirthDateSelect
					year={birthYear}
					month={birthMonth}
					day={birthDay}
					onChange={(next) => {
						setValue("birth_year", next.year, { shouldValidate: true });
						setValue("birth_month", next.month, { shouldValidate: true });
						setValue("birth_day", next.day, { shouldValidate: true });
					}}
				/>
				{errors.birth_day && <span className={styles.error}>{errors.birth_day.message}</span>}
			</div>

			<TextField name="email" label="メールアドレス" type="email" registration={register("email")} error={errors.email?.message} />
			<TextField name="username" label="ユーザー名（ID）" registration={register("username")} error={errors.username?.message} />

			<PasswordField
				name="password"
				label="パスワード"
				registration={register("password")}
				error={errors.password?.message}
				isVisible={showPassword}
				onToggle={() => setShowPassword((current) => !current)}
			/>
			<PasswordStrengthMeter password={password} />
			<PasswordField
				name="password_confirm"
				label="パスワード（確認）"
				registration={register("password_confirm")}
				error={errors.password_confirm?.message}
				isVisible={showPasswordConfirm}
				onToggle={() => setShowPasswordConfirm((current) => !current)}
			/>

			{submitError && <p className={styles.error} role="alert" aria-live="assertive">{submitError}</p>}

			<button className={styles.button} type="submit" disabled={isSubmitting}>
				{isSubmitting ? "登録中…" : "登録する"}
			</button>
		</form>
	);
}

interface TextFieldProps {
	name: keyof RegisterFormValues;
	label: string;
	type?: string;
	registration: ReturnType<ReturnType<typeof useForm<RegisterFormValues>>["register"]>;
	error?: string;
}

function TextField({ name, label, type = "text", registration, error }: TextFieldProps) {
	const errorId = `${name}-error`;
	return (
		<label className={styles.field} htmlFor={name}>
			<span>{label}</span>
			<input
				className={styles.input}
				id={name}
				type={type}
				{...registration}
				aria-required="true"
				aria-invalid={Boolean(error)}
				aria-describedby={error ? errorId : undefined}
			/>
			{error && <span className={styles.error} id={errorId}>{error}</span>}
		</label>
	);
}

function toSubmitPayload(values: RegisterFormValues): RegisterSubmitPayload {
	const { birth_year, birth_month, birth_day, ...rest } = values;
	return {
		...rest,
		birth_date: `${birth_year}-${birth_month.padStart(2, "0")}-${birth_day.padStart(2, "0")}`,
	};
}

function isNetworkError(error: unknown): boolean {
	return error instanceof TypeError || (error !== null && typeof error === "object" && !("status" in error) && !("code" in error) && !("details" in error));
}
