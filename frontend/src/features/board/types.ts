export type TaskStatus = "todo" | "in_progress" | "done";

export interface UserSummary {
	id: string;
	username: string;
	display_name: string;
}

export interface BoardTask {
	id: string;
	project_id: string | null;
	title: string;
	description: string | null;
	status: TaskStatus;
	assignee: UserSummary | null;
	position: number;
	version: number;
	due_at: string | null;
	is_active: boolean;
	created_by: UserSummary;
	comment_count: number;
	created_at: string;
	updated_at: string;
}

export type BoardColumns = Record<TaskStatus, BoardTask[]>;

export interface BoardResponse {
	project_id: string;
	project_is_active: boolean;
	columns: BoardColumns;
}

export const TASK_STATUSES: TaskStatus[] = ["todo", "in_progress", "done"];

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
	todo: "未着手",
	in_progress: "進行中",
	done: "完了",
};
