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
	created_by: UserSummary;
	position: number;
	version: number;
	due_at: string | null;
	comment_count: number;
	created_at: string;
	updated_at: string;
}

export interface BoardResponse {
	columns: Record<TaskStatus, BoardTask[]>;
}
