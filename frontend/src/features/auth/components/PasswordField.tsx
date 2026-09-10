import type { ReactNode } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";

import styles from "./PasswordField.module.css";

export interface PasswordFieldProps {
	name: string;
	label: string;
	registration: UseFormRegisterReturn;
	error?: ReactNode;
	isVisible: boolean;
	onToggle: () => void;
}

/** design doc: docs/detailed_design/screen/01_login.md §3④、§13 aria-label/aria-pressed */
export function PasswordField({ name, label, registration, error, isVisible, onToggle }: PasswordFieldProps) {
	const errorId = `${name}-error`;
	return (
		<div className={styles.field}>
			<label htmlFor={name}>{label}</label>
			<span className={styles.inputRow}>
				<input
					className={styles.input}
					id={name}
					{...registration}
					type={isVisible ? "text" : "password"}
					aria-required="true"
					aria-invalid={Boolean(error)}
					aria-describedby={error ? errorId : undefined}
				/>
				<button
					className={styles.toggle}
					type="button"
					aria-label="パスワードを表示/非表示"
					aria-pressed={isVisible}
					onClick={onToggle}
				>
					{isVisible ? "隠す" : "表示"}
				</button>
			</span>
			{error && (
				<span className={styles.error} id={errorId}>
					{error}
				</span>
			)}
		</div>
	);
}
