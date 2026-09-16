import { useState } from "react";

import {
	DndContext,
	KeyboardSensor,
	PointerSensor,
	closestCenter,
	useSensor,
	useSensors,
	type DragEndEvent,
	type UniqueIdentifier,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";

import type { BoardColumns, BoardTask, TaskStatus } from "../types";
import { TASK_STATUSES, TASK_STATUS_LABELS } from "../types";
import { KanbanColumn } from "./KanbanColumn";
import styles from "./KanbanBoard.module.css";

export interface TaskMoveInput {
	taskId: string;
	status: TaskStatus;
	position: number;
	version: number;
}

interface KanbanBoardProps {
	columns: BoardColumns;
	onTaskMove?: (input: TaskMoveInput) => void;
	onCardClick?: (taskId: string) => void;
	errorMessage?: string | null;
}

interface DropTarget {
	id: UniqueIdentifier;
	data?: { current?: { type?: string; status?: TaskStatus } };
}

interface TaskDropEvent {
	active: { id: UniqueIdentifier };
	over: DropTarget | null;
}

export function KanbanBoard({ columns, onTaskMove, onCardClick = () => undefined, errorMessage }: KanbanBoardProps) {
	const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
	const [statusMessage, setStatusMessage] = useState("カードを選択し、Spaceでドラッグを開始できます。");
	const sensors = useSensors(
		useSensor(PointerSensor),
		useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
	);

	const handleDragStart = ({ active }: { active: { id: UniqueIdentifier } }) => {
		const task = findTask(columns, String(active.id));
		setActiveTaskId(task?.id ?? null);
		if (task) setStatusMessage(`${task.title}をドラッグ中です。移動先でSpaceを押して確定してください。`);
	};

	const handleDragCancel = () => {
		setActiveTaskId(null);
		setStatusMessage("カードの移動をキャンセルしました。");
	};

	const handleDragEnd = (event: DragEndEvent) => {
		setActiveTaskId(null);
		const move = resolveTaskMove(event, columns);
		if (!move) {
			setStatusMessage("カードの移動先が無効なため、移動をキャンセルしました。");
			return;
		}
		onTaskMove?.(move);
		setStatusMessage(`${TASK_STATUS_LABELS[move.status]}列の${move.position + 1}番目に移動しました。`);
	};

	return (
		<section className={styles.board} aria-label="カンバンボード">
			{errorMessage && <p role="alert" className={styles.error}>{errorMessage}</p>}
			<p className={styles.instructions} aria-live="polite">{statusMessage}</p>
			<DndContext
			sensors={sensors}
			collisionDetection={closestCenter}
			onDragStart={handleDragStart}
			onDragCancel={handleDragCancel}
			onDragEnd={handleDragEnd}
			accessibility={{ announcements: createAnnouncements(columns) }}
		>
				<div className={styles.columns}>
					{TASK_STATUSES.map((status) => (
						<KanbanColumn key={status} status={status} tasks={columns[status]} onTaskClick={onCardClick} />
					))}
				</div>
			</DndContext>
			{activeTaskId && <span className={styles.visuallyHidden}>移動中のタスク: {activeTaskId}</span>}
		</section>
	);
}

export function resolveTaskMove(event: TaskDropEvent, columns: BoardColumns): TaskMoveInput | null {
	if (!event.over) return null;
	const task = findTask(columns, String(event.active.id));
	if (!task) return null;

	const targetStatus = getTargetStatus(event.over, columns);
	if (!targetStatus) return null;
	const targetTasks = columns[targetStatus];
	const overTaskIndex = targetTasks.findIndex((targetTask) => targetTask.id === String(event.over?.id));
	const activeIndex = columns[task.status].findIndex((currentTask) => currentTask.id === task.id);
	const position = overTaskIndex >= 0
		? overTaskIndex
		: targetStatus === task.status
			? targetTasks.length - 1
			: targetTasks.length;

	if (position < 0 || (targetStatus === task.status && position === activeIndex)) return null;
	return { taskId: task.id, status: targetStatus, position, version: task.version };
}

function findTask(columns: BoardColumns, taskId: string): BoardTask | undefined {
	return TASK_STATUSES.flatMap((status) => columns[status]).find((task) => task.id === taskId);
}

function getTargetStatus(over: DropTarget, columns: BoardColumns): TaskStatus | null {
	const dataStatus = over.data?.current?.status;
	if (dataStatus && TASK_STATUSES.includes(dataStatus)) return dataStatus;
	const targetTask = findTask(columns, String(over.id));
	if (targetTask) return targetTask.status;
	const targetId = String(over.id);
	if (!targetId.startsWith("column:")) return null;
	const columnStatus = targetId.slice("column:".length) as TaskStatus;
	return TASK_STATUSES.includes(columnStatus) ? columnStatus : null;
}

function createAnnouncements(columns: BoardColumns) {
	return {
		onDragStart({ active }: { active: { id: UniqueIdentifier } }) {
			return findTask(columns, String(active.id))?.title ?? "タスク";
		},
		onDragOver(event: { active: { id: UniqueIdentifier }; over: DropTarget | null }) {
			if (!event.over) return "移動先なし";
			const status = getTargetStatus(event.over, columns);
			return status ? `${TASK_STATUS_LABELS[status]}列上` : "移動先不明";
		},
		onDragEnd(event: { active: { id: UniqueIdentifier }; over: DropTarget | null }) {
			const move = resolveTaskMove(event, columns);
			return move ? `${TASK_STATUS_LABELS[move.status]}列へ移動しました` : "移動をキャンセルしました";
		},
		onDragCancel() {
			return "移動をキャンセルしました";
		},
	};
}
