import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";

import type { BoardTask, TaskStatus } from "../types";
import { TASK_STATUS_LABELS } from "../types";
import { TaskCard } from "./TaskCard";
import styles from "./KanbanColumn.module.css";

interface KanbanColumnProps {
	status: TaskStatus;
	tasks: BoardTask[];
	onTaskClick: (taskId: string) => void;
}

export function KanbanColumn({ status, tasks, onTaskClick }: KanbanColumnProps) {
	const { setNodeRef, isOver } = useDroppable({
		id: columnId(status),
		data: { type: "column", status },
	});

	return (
		<section className={styles.column} aria-labelledby={`column-heading-${status}`}>
			<h2 id={`column-heading-${status}`} className={styles.heading}>
				{TASK_STATUS_LABELS[status]} <span className={styles.count}>{tasks.length}件</span>
			</h2>
			<div ref={setNodeRef} role="list" aria-label={TASK_STATUS_LABELS[status]} className={`${styles.taskList} ${isOver ? styles.over : ""}`}>
				<SortableContext items={tasks.map((task) => task.id)} strategy={verticalListSortingStrategy}>
					{tasks.map((task) => <TaskCard key={task.id} task={task} onClick={onTaskClick} />)}
				</SortableContext>
				{tasks.length === 0 && <p className={styles.empty}>この列にはタスクがありません</p>}
			</div>
		</section>
	);
}

export function columnId(status: TaskStatus): string {
	return `column:${status}`;
}
