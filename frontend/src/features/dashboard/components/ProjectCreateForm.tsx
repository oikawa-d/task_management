import { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../api/errors";
import type { ProjectCreateRequest } from "../api/types";
import { createZodResolver, projectCreateSchema, type ProjectCreateFormValues } from "../validation";

const GENERIC_ERROR_MESSAGE = "プロジェクトの作成に失敗しました。しばらくしてから再度お試しください";

export interface ProjectCreateFormProps {
	onSubmit: (payload: ProjectCreateRequest) => Promise<void>;
	onCancel: () => void;
}

/** 422 VALIDATION_ERROR のfield別エラーをフォームへ反映するための抽出 */
function extractFieldErrors(error: unknown): Array<{ field: string; message: string }> {
	if (!(error instanceof ApiError) || !Array.isArray(error.details)) {
		return [];
	}
	return error.details.filter(
		(item): item is { field: string; message: string } =>
			typeof item === "object" && item !== null && typeof (item as { field?: unknown }).field === "string" && typeof (item as { message?: unknown }).message === "string",
	);
}

/**
 * docs/detailed_design/screen/06_dashboard.md §3（⑨〜⑫）、§9.3、§10、§13
 * name 1〜100文字必須・description 0〜2000文字任意。開いたときnameへ自動フォーカスする。
 */
export function ProjectCreateForm({ onSubmit, onCancel }: ProjectCreateFormProps) {
	const nameRef = useRef<HTMLInputElement | null>(null);
	const {
		register,
		handleSubmit,
		setError,
		formState: { errors, isSubmitting },
	} = useForm<ProjectCreateFormValues>({
		defaultValues: { name: "", description: "" },
		resolver: createZodResolver(projectCreateSchema),
		mode: "onChange",
	});

	useEffect(() => {
		nameRef.current?.focus();
	}, []);

	const submit = async (values: ProjectCreateFormValues) => {
		try {
			await onSubmit({ name: values.name, description: values.description || null });
		} catch (error) {
			const fieldErrors = extractFieldErrors(error);
			if (fieldErrors.length > 0) {
				for (const fieldError of fieldErrors) {
					if (fieldError.field === "name" || fieldError.field === "description") {
						setError(fieldError.field, { type: "server", message: fieldError.message });
					}
				}
				return;
			}
			setError("root", { type: "server", message: GENERIC_ERROR_MESSAGE });
		}
	};

	const nameRegistration = register("name");

	return (
		<form onSubmit={handleSubmit(submit)} noValidate aria-labelledby="create-project-title">
			<h2 id="create-project-title">新規プロジェクトの作成</h2>

			<div>
				<label htmlFor="project-name">プロジェクト名</label>
				<input
					id="project-name"
					{...nameRegistration}
					ref={(element) => {
						nameRegistration.ref(element);
						nameRef.current = element;
					}}
					aria-required="true"
					aria-invalid={Boolean(errors.name)}
					aria-describedby={errors.name ? "project-name-error" : undefined}
				/>
				{errors.name && (
					<span id="project-name-error" role="alert">
						{errors.name.message}
					</span>
				)}
			</div>

			<div>
				<label htmlFor="project-description">説明</label>
				<textarea
					id="project-description"
					{...register("description")}
					aria-invalid={Boolean(errors.description)}
					aria-describedby={errors.description ? "project-description-error" : undefined}
				/>
				{errors.description && (
					<span id="project-description-error" role="alert">
						{errors.description.message}
					</span>
				)}
			</div>

			{errors.root && (
				<p role="alert" aria-live="assertive">
					{errors.root.message}
				</p>
			)}

			<button type="submit" disabled={isSubmitting}>
				作成
			</button>
			<button type="button" onClick={onCancel}>
				キャンセル
			</button>
		</form>
	);
}
