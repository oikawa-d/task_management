import type { KeyboardEvent } from "react";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import type { BoardTask } from "../types";
import styles from "./TaskCard.module.css";

interface TaskCardProps {
	task: BoardTask;
	onClick: (taskId: string) => void;
}

export function TaskCard({ task, onClick }: TaskCardProps) {
	const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
		id: task.id,
		data: { type: "task", status: task.status },
		attributes: { role: "listitem", roleDescription: "draggable item", tabIndex: 0 },
	});

	const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
		if (event.key === "Enter") {
			event.preventDefault();
			onClick(task.id);
			return;
		}
		listeners?.onKeyDown?.(event);
	};

	return (
		<article
			ref={setNodeRef}
			{...attributes}
			{...listeners}
			onKeyDown={handleKeyDown}
			onClick={() => onClick(task.id)}
			className={`${styles.card} ${isDragging ? styles.dragging : ""}`}
			style={{ transform: CSS.Transform.toString(transform), transition }}
			aria-label={`${task.title}。担当者 ${task.assignee?.display_name ?? "未割当"}`}
		>
			<h3 className={styles.title}>{task.title}</h3>
			<p className={styles.detail}>担当者: {task.assignee?.display_name ?? "未割当"}</p>
			<p className={styles.detail}>期限: {formatDueAt(task.due_at)}</p>
			<p className={styles.detail}>コメント: {task.comment_count}件</p>
		</article>
	);
}

function formatDueAt(dueAt: string | null): string {
	if (!dueAt) return "なし";
	const date = new Date(dueAt);
	if (Number.isNaN(date.getTime())) return "日付を確認できません";
	return new Intl.DateTimeFormat("ja-JP", { year: "numeric", month: "long", day: "numeric" }).format(date);
}
