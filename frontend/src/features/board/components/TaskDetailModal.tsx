import { useEffect, useRef } from "react";

import type { BoardTask, TaskStatus } from "../types";
import styles from "./TaskDetailModal.module.css";

const STATUS_LABELS: Record<TaskStatus, string> = {
	todo: "未着手",
	in_progress: "進行中",
	done: "完了",
};

interface TaskDetailModalProps {
	projectId: string;
	taskId: string;
	task?: BoardTask;
	isLoading?: boolean;
	onClose: () => void;
}

export function TaskDetailModal({ task, isLoading = false, onClose }: TaskDetailModalProps) {
	const dialogRef = useRef<HTMLDivElement>(null);
	const titleInputRef = useRef<HTMLInputElement>(null);
	const previousFocus = useRef<HTMLElement | null>(null);

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
		if (!task) return;
		titleInputRef.current?.focus();
	}, [task]);

	useEffect(() => {
		const dialog = dialogRef.current;
		if (!dialog) return;
		const focusable = () =>
			Array.from(dialog.querySelectorAll<HTMLElement>("button, input, textarea, select, [tabindex='0']")).filter(
				(element) => !element.hasAttribute("disabled"),
			);
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

	return (
		<div className={styles.overlay}>
			<div ref={dialogRef} className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="task-detail-title">
				<header className={styles.header}>
					<h1 id="task-detail-title">タスク詳細</h1>
					<button type="button" aria-label="閉じる" onClick={onClose}>×</button>
				</header>
				{isLoading && <p role="status">読み込み中...</p>}
				{!isLoading && !task && <NotFoundState onClose={onClose} />}
				{task && (
					<>
						<div className={styles.fields}>
							<label>タイトル<input ref={titleInputRef} defaultValue={task.title} maxLength={150} readOnly /></label>
							<label>説明<textarea defaultValue={task.description ?? ""} maxLength={2000} rows={4} readOnly /></label>
							<div className={styles.row}>
								<label>担当者<select defaultValue={task.assignee?.id ?? ""} disabled><option value="">未割当</option>{task.assignee && <option value={task.assignee.id}>{task.assignee.display_name}</option>}</select></label>
								<label>期限<input type="datetime-local" defaultValue={task.due_at?.slice(0, 16) ?? ""} readOnly /></label>
							</div>
							<label>ステータス<select defaultValue={task.status} disabled>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
						</div>
						<section aria-labelledby="comments-title" className={styles.comments}>
							<h2 id="comments-title">コメント</h2>
							<p className={styles.placeholder}>コメント一覧・投稿は準備中です。</p>
						</section>
						<button type="button" className={styles.delete} disabled>タスクを削除</button>
					</>
				)}
			</div>
		</div>
	);
}

function NotFoundState({ onClose }: Pick<TaskDetailModalProps, "onClose">) {
	return <div><p>タスクが見つかりません</p><button type="button" onClick={onClose}>ボードへ戻る</button></div>;
}
