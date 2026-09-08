import { useState } from "react";

import styles from "./PasswordChangeForm.module.css";
import type { PasswordChangeInput } from "./types";
import { getApiErrorCode, getFieldErrors, validatePassword } from "./validation";

export interface PasswordChangeFormProps {
	hasPassword: boolean;
	onSubmit: (values: PasswordChangeInput) => Promise<void>;
	onSuccess?: () => void;
}

type PasswordField = keyof PasswordChangeInput;

export function PasswordChangeForm({ hasPassword, onSubmit, onSuccess }: PasswordChangeFormProps) {
	const [values, setValues] = useState<PasswordChangeInput>({
		...(hasPassword ? { current_password: "" } : {}),
		new_password: "",
		password_confirm: "",
	});
	const [visible, setVisible] = useState<Record<PasswordField, boolean>>({
		current_password: false,
		new_password: false,
		password_confirm: false,
	});
	const [errors, setErrors] = useState(() => validatePassword(values, hasPassword));
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [isSaved, setIsSaved] = useState(false);

	const updateField = (field: PasswordField, value: string) => {
		const nextValues = { ...values, [field]: value };
		setValues(nextValues);
		setErrors(validatePassword(nextValues, hasPassword));
		setSubmitError(null);
		setIsSaved(false);
	};

	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const nextErrors = validatePassword(values, hasPassword);
		setErrors(nextErrors);
		if (Object.keys(nextErrors).length > 0) {
			return;
		}

		const payload = hasPassword
			? values
			: { new_password: values.new_password, password_confirm: values.password_confirm };
		setSubmitError(null);
		setIsSaved(false);
		setIsSubmitting(true);
		try {
			await onSubmit(payload);
			const resetValues: PasswordChangeInput = {
				...(hasPassword ? { current_password: "" } : {}),
				new_password: "",
				password_confirm: "",
			};
			setValues({
				...(hasPassword ? { current_password: "" } : {}),
				new_password: "",
				password_confirm: "",
			});
			setErrors(validatePassword(resetValues, hasPassword));
			setIsSaved(true);
			onSuccess?.();
		} catch (error: unknown) {
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				setErrors((current) => ({
					...current,
					...Object.fromEntries(fieldErrors.map(({ field, message }) => [field, message])),
				}));
			} else if (isInvalidCredentials(error)) {
				setErrors((current) => ({ ...current, current_password: "現在のパスワードが正しくありません" }));
			} else {
				setSubmitError("パスワードの変更に失敗しました");
			}
		} finally {
			setIsSubmitting(false);
		}
	};

	return (
		<form className={styles.form} onSubmit={handleSubmit} noValidate>
			{hasPassword && (
				<PasswordFieldInput
					field="current_password"
					label="現在のパスワード"
					value={values.current_password ?? ""}
					error={errors.current_password}
					isVisible={visible.current_password}
					onToggle={() => setVisible((current) => ({ ...current, current_password: !current.current_password }))}
					onChange={(value) => updateField("current_password", value)}
				/>
			)}
			<PasswordFieldInput
				field="new_password"
				label="新しいパスワード"
				value={values.new_password}
				error={errors.new_password}
				isVisible={visible.new_password}
				onToggle={() => setVisible((current) => ({ ...current, new_password: !current.new_password }))}
				onChange={(value) => updateField("new_password", value)}
			/>
			<PasswordFieldInput
				field="password_confirm"
				label="新しいパスワード（確認）"
				value={values.password_confirm}
				error={errors.password_confirm}
				isVisible={visible.password_confirm}
				onToggle={() => setVisible((current) => ({ ...current, password_confirm: !current.password_confirm }))}
				onChange={(value) => updateField("password_confirm", value)}
			/>
			{submitError && <p className={styles.submitError} role="alert">{submitError}</p>}
			{isSaved && <p className={styles.success} role="status">パスワードを変更しました</p>}
			<button className={styles.button} type="submit" disabled={isSubmitting || Object.keys(errors).length > 0}>
				{isSubmitting ? "変更中…" : "パスワードを変更"}
			</button>
		</form>
	);
}

interface PasswordFieldInputProps {
	field: PasswordField;
	label: string;
	value: string;
	error?: string;
	isVisible: boolean;
	onToggle: () => void;
	onChange: (value: string) => void;
}

function PasswordFieldInput({ field, label, value, error, isVisible, onToggle, onChange }: PasswordFieldInputProps) {
	const errorId = `${field}-error`;
	return (
		<div className={styles.field}>
			<label htmlFor={field}>{label}</label>
			<span className={styles.passwordInput}>
				<input
					className={styles.input}
					id={field}
					name={field}
					type={isVisible ? "text" : "password"}
					value={value}
					aria-invalid={Boolean(error)}
					aria-describedby={error ? errorId : undefined}
					onChange={(event) => onChange(event.target.value)}
				/>
				<button className={styles.toggle} type="button" aria-label="パスワードを表示/非表示" onClick={onToggle}>
					{isVisible ? "隠す" : "表示"}
				</button>
			</span>
			{error && <span className={styles.error} id={errorId}>{error}</span>}
		</div>
	);
}

function isInvalidCredentials(error: unknown): boolean {
	return getApiErrorCode(error) === "INVALID_CREDENTIALS";
}
