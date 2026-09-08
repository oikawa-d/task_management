import type { BoardTask } from "../types";

interface TaskCardProps {
	task: BoardTask;
	onClick: (taskId: string) => void;
}

export function TaskCard({ task, onClick }: TaskCardProps) {
	return (
		<button type="button" className="task-card" onClick={() => onClick(task.id)}>
			<strong>{task.title}</strong>
			<span>{task.assignee?.display_name ?? "未割当"}</span>
		</button>
	);
}
