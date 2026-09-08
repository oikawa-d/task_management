export type TaskStatus = "todo" | "in_progress" | "done";

export interface BoardTaskSummary {
	id: string;
	title: string;
}

export interface BoardColumns {
	todo: BoardTaskSummary[];
	in_progress: BoardTaskSummary[];
	done: BoardTaskSummary[];
}

export interface BoardResponse {
	columns: BoardColumns;
}
