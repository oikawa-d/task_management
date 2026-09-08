import { useState, type ReactNode } from "react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";

import styles from "./PasswordChangeForm.module.css";
import type { PasswordChangeInput } from "./types";
import { createZodResolver, getFieldErrors, passwordSchema } from "./validation";

export interface PasswordChangeFormProps {
	hasPassword: boolean;
	onSubmit: (values: PasswordChangeInput) => Promise<void>;
	onSuccess?: () => void;
}

type PasswordField = keyof PasswordChangeInput;

export function PasswordChangeForm({ hasPassword, onSubmit, onSuccess }: PasswordChangeFormProps) {
	const [visible, setVisible] = useState<Record<PasswordField, boolean>>({
		current_password: false,
		new_password: false,
		password_confirm: false,
	});
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [isSaved, setIsSaved] = useState(false);
	const {
		register,
		handleSubmit,
		reset,
		setError,
		watch,
		formState: { errors, isSubmitting },
	} = useForm<PasswordChangeInput>({
		defaultValues: createDefaultValues(hasPassword),
		resolver: createZodResolver(passwordSchema(hasPassword)),
		mode: "onChange",
	});
	const currentPassword = watch("current_password");

	const submit = async (values: PasswordChangeInput) => {
		setSubmitError(null);
		setIsSaved(false);
		try {
			await onSubmit(hasPassword ? values : omitCurrentPassword(values));
			reset(createDefaultValues(hasPassword));
			setIsSaved(true);
			onSuccess?.();
		} catch (error: unknown) {
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				for (const fieldError of fieldErrors) {
					if (isPasswordField(fieldError.field)) {
						setError(fieldError.field, { type: "server", message: fieldError.message });
					}
				}
			} else if (isInvalidCredentials(error) && hasPassword) {
				setError("current_password", { type: "server", message: "現在のパスワードが正しくありません" });
			} else if (isInvalidCredentials(error)) {
				setSubmitError("パスワードを変更できませんでした。再度ログインしてからお試しください");
			} else {
				setSubmitError("パスワードの変更に失敗しました");
			}
		}
	};

	return (
		<form className={styles.form} onSubmit={handleSubmit(submit)} noValidate>
			{hasPassword && (
				<PasswordFieldInput
					field="current_password"
					label="現在のパスワード"
					registration={register("current_password")}
					error={errors.current_password?.message}
					isVisible={visible.current_password}
					onToggle={() => setVisible((current) => ({ ...current, current_password: !current.current_password }))}
				/>
			)}
			<PasswordFieldInput
				field="new_password"
				label="新しいパスワード"
				registration={register("new_password")}
				error={errors.new_password?.message}
				isVisible={visible.new_password}
				onToggle={() => setVisible((current) => ({ ...current, new_password: !current.new_password }))}
			/>
			<PasswordFieldInput
				field="password_confirm"
				label="新しいパスワード（確認）"
				registration={register("password_confirm")}
				error={errors.password_confirm?.message}
				isVisible={visible.password_confirm}
				onToggle={() => setVisible((current) => ({ ...current, password_confirm: !current.password_confirm }))}
			/>
			{submitError && <p className={styles.submitError} role="alert">{submitError}</p>}
			{isSaved && <p className={styles.success} role="status">パスワードを変更しました</p>}
			<button
				className={styles.button}
				type="submit"
				disabled={isSubmitting || (hasPassword && !currentPassword) || Object.keys(errors).length > 0}
			>
				{isSubmitting ? "変更中…" : "パスワードを変更"}
			</button>
		</form>
	);
}

interface PasswordFieldInputProps {
	field: PasswordField;
	label: string;
	registration: UseFormRegisterReturn;
	error?: ReactNode;
	isVisible: boolean;
	onToggle: () => void;
}

function PasswordFieldInput({ field, label, registration, error, isVisible, onToggle }: PasswordFieldInputProps) {
	const errorId = `${field}-error`;
	return (
		<div className={styles.field}>
			<label htmlFor={field}>{label}</label>
			<span className={styles.passwordInput}>
				<input
					className={styles.input}
					id={field}
					{...registration}
					type={isVisible ? "text" : "password"}
					aria-invalid={Boolean(error)}
					aria-describedby={error ? errorId : undefined}
				/>
				<button className={styles.toggle} type="button" aria-label="パスワードを表示/非表示" onClick={onToggle}>
					{isVisible ? "隠す" : "表示"}
				</button>
			</span>
			{error && <span className={styles.error} id={errorId}>{error}</span>}
		</div>
	);
}

function createDefaultValues(hasPassword: boolean): PasswordChangeInput {
	return {
		...(hasPassword ? { current_password: "" } : {}),
		new_password: "",
		password_confirm: "",
	};
}

function omitCurrentPassword(values: PasswordChangeInput): PasswordChangeInput {
	return { new_password: values.new_password, password_confirm: values.password_confirm };
}

function isPasswordField(field: string): field is PasswordField {
	return ["current_password", "new_password", "password_confirm"].includes(field);
}

function isInvalidCredentials(error: unknown): boolean {
	return Boolean(error && typeof error === "object" && "code" in error && error.code === "INVALID_CREDENTIALS");
}
