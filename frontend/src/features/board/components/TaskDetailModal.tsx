import { useEffect, useRef } from "react";

import { useAuthStore } from "../../../auth/authStore";
import type { TaskDetailApiError, TaskUpdateFields } from "../../../lib/api/taskDetail";
import { CommentForm } from "../../task-detail/components/CommentForm";
import { CommentList } from "../../task-detail/components/CommentList";
import { TaskEditForm, type TaskEditFormValues, type TaskMember } from "../../task-detail/components/TaskEditForm";
import { useTaskDetail } from "../../task-detail/hooks/useTaskDetail";
import styles from "./TaskDetailModal.module.css";

interface TaskDetailModalProps {
	projectId: string;
	taskId: string;
	onClose: () => void;
}

export function TaskDetailModal({ taskId, onClose }: TaskDetailModalProps) {
	const dialogRef = useRef<HTMLDivElement>(null);
	const titleInputRef = useRef<HTMLInputElement>(null);
	const previousFocus = useRef<HTMLElement | null>(null);
	const user = useAuthStore((state) => state.user);
	const detail = useTaskDetail(taskId, { onClose });

	useEffect(() => {
		previousFocus.current = document.activeElement as HTMLElement | null;
		const previousOverflow = document.body.style.overflow;
		document.body.style.overflow = "hidden";
		return () => {
			document.body.style.overflow = previousOverflow;
			previousFocus.current?.focus();
		};
	}, []);

	useEffect(() => {
		if (detail.task) titleInputRef.current?.focus();
	}, [detail.task]);

	useEffect(() => {
		const dialog = dialogRef.current;
		if (!dialog) return;
		const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>(
			"button, input, textarea, select, [tabindex='0']",
		)).filter((element) => !element.hasAttribute("disabled"));
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") return onClose();
			if (event.key !== "Tab") return;
			const elements = focusable();
			if (elements.length === 0) return;
			const first = elements[0];
			const last = elements[elements.length - 1];
			if (event.shiftKey && document.activeElement === first) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault();
				first.focus();
			}
		};
		dialog.addEventListener("keydown", onKeyDown);
		return () => dialog.removeEventListener("keydown", onKeyDown);
	}, [onClose]);

	const errorMessage = getErrorMessage(detail.error);
	const commentsError = getErrorMessage(detail.commentsError);
	const task = detail.task;

	return (
		<div className={styles.overlay}>
			<div ref={dialogRef} className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="task-detail-title">
				<header className={styles.header}>
					<h1 id="task-detail-title">タスク詳細</h1>
					<button type="button" aria-label="閉じる" onClick={onClose}>×</button>
				</header>
				{detail.isLoading && <p role="status">読み込み中...</p>}
				{!detail.isLoading && detail.notFound && (!task || !detail.commentsError) && <NotFoundState onClose={onClose} />}
				{!detail.isLoading && !task && !detail.notFound && detail.error && <ErrorState message={errorMessage} onRetry={detail.refresh} />}
				{task && (!detail.notFound || Boolean(detail.commentsError)) && (
					<>
						{detail.conflictBannerVisible && (
							<p role="alert">他のユーザーが更新したため最新の内容を再取得しました</p>
						)}
						<TaskEditForm
							task={toFormValues(task)}
							members={getMembers(task)}
							isSaving={detail.isSaving}
							titleInputRef={titleInputRef}
							onUpdate={(field, value) => void detail.updateTask(toUpdateFields(field, value))}
						/>
						{detail.error && <p role="alert">{errorMessage}</p>}
						<section aria-labelledby="comments-title" className={styles.comments}>
							<h2 id="comments-title">コメント</h2>
							{detail.notFound && detail.commentsError ? (
								<p role="alert">コメントが見つかりません</p>
							) : (
								<CommentList
									comments={detail.comments}
									currentUserId={user?.id ?? ""}
									currentUserRole={user?.role ?? "member"}
									error={commentsError}
									onEdit={(commentId, body) => detail.updateComment(commentId, body)}
									onDelete={(commentId) => detail.removeComment(taskId, commentId)}
								/>
							)}
							<CommentForm
								onSubmit={(body) => detail.addComment(body)}
								isSubmitting={detail.isSaving}
							/>
						</section>
						<button
							type="button"
							className={styles.delete}
							disabled={detail.isSaving}
							onClick={() => window.confirm("このタスクを削除しますか？") && void detail.removeTask()}
						>
							タスクを削除
						</button>
					</>
				)}
			</div>
		</div>
	);
}

function toFormValues(task: NonNullable<ReturnType<typeof useTaskDetail>["task"]>): TaskEditFormValues {
	return {
		title: task.title,
		description: task.description,
		assignee_id: task.assignee?.id ?? null,
		due_at: task.due_at?.slice(0, 16) ?? null,
		status: task.status,
	};
}

function getMembers(task: NonNullable<ReturnType<typeof useTaskDetail>["task"]>): TaskMember[] {
	return task.assignee ? [{ ...task.assignee, is_active: true }] : [];
}

function toUpdateFields(field: Parameters<NonNullable<React.ComponentProps<typeof TaskEditForm>["onUpdate"]>>[0], value: string | null): TaskUpdateFields {
	if (field === "title") return { title: value ?? "" };
	if (field === "description") return { description: value };
	if (field === "assignee_id") return { assignee_id: value };
	if (field === "due_at") return { due_at: value };
	return { status: value as TaskUpdateFields["status"] };
}

function getErrorMessage(error: TaskDetailApiError | Error | null): string | undefined {
	if (!error) return undefined;
	if (!("status" in error)) return "エラーが発生しました。しばらくしてから再度お試しください";
	if (error.status >= 500 || error.status === 0) return "エラーが発生しました。しばらくしてから再度お試しください";
	if (error.code === "ASSIGNEE_INACTIVE") return "指定した担当者は無効化されています";
	if (error.status === 403) return "この操作を行う権限がありません";
	if (error.status === 422) return error.message || "入力内容を確認してください";
	return error.message || "エラーが発生しました。しばらくしてから再度お試しください";
}

function NotFoundState({ onClose }: Pick<TaskDetailModalProps, "onClose">) {
	return <div><p>タスクが見つかりません</p><button type="button" onClick={onClose}>ボードへ戻る</button></div>;
}

function ErrorState({ message, onRetry }: { message?: string; onRetry: () => Promise<void> }) {
	return <div><p role="alert">{message}</p><button type="button" onClick={() => void onRetry()}>再取得</button></div>;
}
