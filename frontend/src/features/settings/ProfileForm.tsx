import { useEffect, useMemo, useState } from "react";

import styles from "./ProfileForm.module.css";
import type { ProfileFormValues, ProfilePatchInput } from "./types";
import { getFieldErrors, getToday, validateProfile } from "./validation";

export interface ProfileFormProps {
	initialValues: ProfileFormValues;
	onSubmit: (values: ProfilePatchInput) => Promise<void>;
	onSaved?: (values: ProfilePatchInput) => void;
}

const FIELD_LABELS: Record<keyof ProfileFormValues, string> = {
	last_name: "姓",
	first_name: "名",
	last_name_kana: "姓カナ",
	first_name_kana: "名カナ",
	birth_date: "生年月日",
};

export function ProfileForm({ initialValues, onSubmit, onSaved }: ProfileFormProps) {
	const normalizedInitialValues = useMemo(() => normalizeValues(initialValues), [initialValues]);
	const [values, setValues] = useState(normalizedInitialValues);
	const [baseline, setBaseline] = useState(normalizedInitialValues);
	const [errors, setErrors] = useState(() => validateProfile(normalizedInitialValues));
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [isSaved, setIsSaved] = useState(false);

	useEffect(() => {
		setValues(normalizedInitialValues);
		setBaseline(normalizedInitialValues);
		setErrors(validateProfile(normalizedInitialValues));
		setIsSaved(false);
	}, [normalizedInitialValues]);

	const isDirty = !areValuesEqual(values, baseline);
	const canSubmit = isDirty && Object.keys(errors).length === 0 && !isSubmitting;

	const updateField = (field: keyof ProfileFormValues, value: string) => {
		const nextValues = { ...values, [field]: value };
		setValues(nextValues);
		setErrors(validateProfile(nextValues));
		setSubmitError(null);
		setIsSaved(false);
	};

	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const nextErrors = validateProfile(values);
		setErrors(nextErrors);
		if (Object.keys(nextErrors).length > 0 || !isDirty) {
			return;
		}

		const patch = createPatch(values, baseline);
		setSubmitError(null);
		setIsSaved(false);
		setIsSubmitting(true);
		try {
			await onSubmit(patch);
			setBaseline(values);
			setIsSaved(true);
			onSaved?.(patch);
		} catch (error: unknown) {
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				setErrors((current) => ({
					...current,
					...Object.fromEntries(fieldErrors.map(({ field, message }) => [field, message])),
				}));
			} else {
				setSubmitError("プロフィールの更新に失敗しました");
			}
		} finally {
			setIsSubmitting(false);
		}
	};

	return (
		<form className={styles.form} onSubmit={handleSubmit} noValidate>
			{(Object.keys(FIELD_LABELS) as Array<keyof ProfileFormValues>).map((field) => (
				<ProfileField
					key={field}
					field={field}
					label={FIELD_LABELS[field]}
					value={values[field] ?? ""}
					error={errors[field]}
					onChange={(value) => updateField(field, value)}
				/>
			))}
			{submitError && <p className={styles.submitError} role="alert">{submitError}</p>}
			{isSaved && <p className={styles.success} role="status">プロフィールを更新しました</p>}
			<button className={styles.button} type="submit" disabled={!canSubmit}>
				{isSubmitting ? "保存中…" : "プロフィールを保存"}
			</button>
		</form>
	);
}

interface ProfileFieldProps {
	field: keyof ProfileFormValues;
	label: string;
	value: string;
	error?: string;
	onChange: (value: string) => void;
}

function ProfileField({ field, label, value, error, onChange }: ProfileFieldProps) {
	const errorId = `${field}-error`;
	return (
		<label className={styles.field} htmlFor={field}>
			<span>{label}</span>
			<input
				className={styles.input}
				id={field}
				name={field}
				type={field === "birth_date" ? "date" : "text"}
				value={value}
				max={field === "birth_date" ? getToday() : undefined}
				aria-invalid={Boolean(error)}
				aria-describedby={error ? errorId : undefined}
				onChange={(event) => onChange(event.target.value)}
			/>
			{error && <span className={styles.error} id={errorId}>{error}</span>}
		</label>
	);
}

function normalizeValues(values: ProfileFormValues): ProfileFormValues {
	return {
		last_name: values.last_name ?? "",
		first_name: values.first_name ?? "",
		last_name_kana: values.last_name_kana ?? "",
		first_name_kana: values.first_name_kana ?? "",
		birth_date: values.birth_date ?? "",
	};
}

function areValuesEqual(left: ProfileFormValues, right: ProfileFormValues): boolean {
	return (Object.keys(FIELD_LABELS) as Array<keyof ProfileFormValues>).every(
		(field) => left[field] === right[field],
	);
}

function createPatch(values: ProfileFormValues, baseline: ProfileFormValues): ProfilePatchInput {
	return Object.fromEntries(
		(Object.keys(FIELD_LABELS) as Array<keyof ProfileFormValues>)
			.filter((field) => values[field] !== baseline[field])
			.map((field) => [field, values[field] as string]),
	) as ProfilePatchInput;
}
