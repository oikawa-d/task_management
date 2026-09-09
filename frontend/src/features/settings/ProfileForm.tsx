import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import styles from "./ProfileForm.module.css";
import type { ProfileFormValues, ProfilePatchInput } from "./types";
import { createZodResolver, getFieldErrors, getToday, profileSchema } from "./validation";

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

type FormValues = {
	[field in keyof ProfileFormValues]: string;
};

export function ProfileForm({ initialValues, onSubmit, onSaved }: ProfileFormProps) {
	const normalizedInitialValues = useMemo(() => normalizeValues(initialValues), [initialValues]);
	const [baseline, setBaseline] = useState(normalizedInitialValues);
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [isSaved, setIsSaved] = useState(false);
	const {
		register,
		handleSubmit,
		reset,
		setError,
		formState: { errors, isDirty, isSubmitting },
	} = useForm<FormValues>({
		defaultValues: normalizedInitialValues,
		resolver: createZodResolver(profileSchema),
		mode: "onChange",
	});

	useEffect(() => {
		reset(normalizedInitialValues);
		setBaseline(normalizedInitialValues);
		setSubmitError(null);
		setIsSaved(false);
	}, [normalizedInitialValues, reset]);

	const submit = async (values: FormValues) => {
		const patch = createPatch(values, baseline);
		setSubmitError(null);
		setIsSaved(false);
		try {
			await onSubmit(patch);
			setBaseline(values);
			reset(values);
			setIsSaved(true);
			onSaved?.(patch);
		} catch (error: unknown) {
			const fieldErrors = getFieldErrors(error);
			if (fieldErrors.length > 0) {
				for (const fieldError of fieldErrors) {
					if (fieldError.field in FIELD_LABELS) {
						setError(fieldError.field as keyof FormValues, { type: "server", message: fieldError.message });
					}
				}
			} else {
				setSubmitError("プロフィールの更新に失敗しました");
			}
		}
	};

	return (
		<form className={styles.form} onSubmit={handleSubmit(submit)} noValidate>
			{(Object.keys(FIELD_LABELS) as Array<keyof FormValues>).map((field) => (
				<ProfileField
					key={field}
					field={field}
					label={FIELD_LABELS[field]}
					registration={register(field)}
					error={errors[field]?.message}
				/>
			))}
			{submitError && <p className={styles.submitError} role="alert">{submitError}</p>}
			{isSaved && <p className={styles.success} role="status">プロフィールを更新しました</p>}
			<button className={styles.button} type="submit" disabled={!isDirty || Object.keys(errors).length > 0 || isSubmitting}>
				{isSubmitting ? "保存中…" : "プロフィールを保存"}
			</button>
		</form>
	);
}

interface ProfileFieldProps {
	field: keyof FormValues;
	label: string;
	registration: ReturnType<ReturnType<typeof useForm<FormValues>>["register"]>;
	error?: string;
}

function ProfileField({ field, label, registration, error }: ProfileFieldProps) {
	const errorId = `${field}-error`;
	return (
		<label className={styles.field} htmlFor={field}>
			<span>{label}</span>
			<input
				className={styles.input}
				id={field}
				type={field === "birth_date" ? "date" : "text"}
				max={field === "birth_date" ? getToday() : undefined}
				aria-invalid={Boolean(error)}
				aria-describedby={error ? errorId : undefined}
				{...registration}
			/>
			{error && <span className={styles.error} id={errorId}>{error}</span>}
		</label>
	);
}

function normalizeValues(values: ProfileFormValues): FormValues {
	return {
		last_name: values.last_name ?? "",
		first_name: values.first_name ?? "",
		last_name_kana: values.last_name_kana ?? "",
		first_name_kana: values.first_name_kana ?? "",
		birth_date: values.birth_date ?? "",
	};
}

function createPatch(values: FormValues, baseline: FormValues): ProfilePatchInput {
	return Object.fromEntries(
		(Object.keys(FIELD_LABELS) as Array<keyof FormValues>)
			.filter((field) => values[field] !== baseline[field])
			.map((field) => [field, values[field]]),
	) as ProfilePatchInput;
}
