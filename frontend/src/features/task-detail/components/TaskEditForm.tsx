import { useEffect, useState } from "react";

import { getConfiguredTaskDescriptionMaxLength, getConfiguredTaskTitleMaxLength } from "./formConfig";

export type TaskStatus = "todo" | "in_progress" | "done";
export type TaskEditableField = "title" | "description" | "assignee_id" | "due_at" | "status";

export interface TaskEditFormValues {
	title: string;
	description: string | null;
	assignee_id: string | null;
	due_at: string | null;
	status: TaskStatus;
}

export interface TaskMember {
	id: string;
	display_name: string;
	is_active: boolean;
}

export interface TaskEditFormProps {
	task: TaskEditFormValues;
	members: TaskMember[];
	fieldErrors?: Partial<Record<TaskEditableField, string>>;
	isSaving?: boolean;
	onUpdate: (field: TaskEditableField, value: string | null) => void;
}

const STATUS_LABELS: Record<TaskStatus, string> = {
	todo: "未着手",
	in_progress: "進行中",
	done: "完了",
};

export function TaskEditForm({
	task,
	members,
	fieldErrors = {},
	isSaving = false,
	onUpdate,
}: TaskEditFormProps) {
	const TITLE_MAX_LENGTH = getConfiguredTaskTitleMaxLength();
	const DESCRIPTION_MAX_LENGTH = getConfiguredTaskDescriptionMaxLength();
	const [title, setTitle] = useState(task.title);
	const [description, setDescription] = useState(task.description ?? "");
	const [localErrors, setLocalErrors] = useState<Partial<Record<TaskEditableField, string>>>({});

	useEffect(() => {
		setTitle(task.title);
		setDescription(task.description ?? "");
	}, [task.title, task.description]);

	const setError = (field: TaskEditableField, message?: string) => {
		setLocalErrors((current) => ({ ...current, [field]: message }));
	};

	const validateText = (field: "title" | "description", value: string): boolean => {
		const invalid =
			(field === "title" && (value.length < 1 || value.length > TITLE_MAX_LENGTH)) ||
			(field === "description" && value.length > DESCRIPTION_MAX_LENGTH);
		if (invalid) {
			setError(
				field,
				field === "title"
					? `タイトルは1〜${TITLE_MAX_LENGTH}文字で入力してください`
					: `説明は${DESCRIPTION_MAX_LENGTH}文字以内で入力してください`,
			);
			return false;
		}
		setError(field);
		return true;
	};

	const handleTextBlur = (field: "title" | "description", value: string) => {
		if (!validateText(field, value)) return;
		const original = field === "title" ? task.title : task.description ?? "";
		if (value !== original) onUpdate(field, value);
	};

	const handleSelectChange = (field: "assignee_id" | "status", value: string) => {
		setError(field);
		const normalized = field === "assignee_id" ? value || null : (value as TaskStatus);
		const original = field === "assignee_id" ? task.assignee_id : task.status;
		if (normalized !== original) onUpdate(field, normalized);
	};

	const handleDueAtChange = (value: string) => {
		setError("due_at");
		const normalized = value || null;
		if (normalized !== task.due_at) onUpdate("due_at", normalized);
	};

	const errorFor = (field: TaskEditableField) => localErrors[field] ?? fieldErrors[field];

	return (
		<form aria-label="タスク編集" onSubmit={(event) => event.preventDefault()}>
			<label>
				タイトル
				<input
					value={title}
					maxLength={TITLE_MAX_LENGTH}
					onChange={(event) => setTitle(event.target.value)}
					onBlur={(event) => handleTextBlur("title", event.target.value)}
					aria-invalid={Boolean(errorFor("title"))}
					disabled={isSaving}
				/>
			</label>
			{errorFor("title") && <p role="alert">{errorFor("title")}</p>}

			<label>
				説明
				<textarea
					value={description}
					maxLength={DESCRIPTION_MAX_LENGTH}
					rows={4}
					onChange={(event) => setDescription(event.target.value)}
					onBlur={(event) => handleTextBlur("description", event.target.value)}
					aria-invalid={Boolean(errorFor("description"))}
					disabled={isSaving}
				/>
			</label>
			{errorFor("description") && <p role="alert">{errorFor("description")}</p>}

			<label>
				担当者
				<select
					value={task.assignee_id ?? ""}
					onChange={(event) => handleSelectChange("assignee_id", event.target.value)}
					disabled={isSaving}
				>
					<option value="">未割当</option>
					{members.map((member) => (
						<option key={member.id} value={member.id} disabled={!member.is_active}>
							{member.display_name}{member.is_active ? "" : "（無効）"}
						</option>
					))}
				</select>
			</label>
			{errorFor("assignee_id") && <p role="alert">{errorFor("assignee_id")}</p>}

			<label>
				期限
				<input
					type="datetime-local"
					value={task.due_at ?? ""}
					onChange={(event) => handleDueAtChange(event.target.value)}
					disabled={isSaving}
					aria-invalid={Boolean(errorFor("due_at"))}
				/>
			</label>
			{errorFor("due_at") && <p role="alert">{errorFor("due_at")}</p>}

			<label>
				ステータス
				<select
					value={task.status}
					onChange={(event) => handleSelectChange("status", event.target.value)}
					disabled={isSaving}
				>
					{Object.entries(STATUS_LABELS).map(([value, label]) => (
						<option key={value} value={value}>
							{label}
						</option>
					))}
				</select>
			</label>
			{errorFor("status") && <p role="alert">{errorFor("status")}</p>}
		</form>
	);
}
