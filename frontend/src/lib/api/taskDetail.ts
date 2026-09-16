import { requestJson } from "../../api/http";

export type TaskStatus = "todo" | "in_progress" | "done";

export interface UserSummary {
	id: string;
	username: string;
	display_name: string;
}

export interface TaskDetail {
	id: string;
	project_id: string | null;
	title: string;
	description: string | null;
	status: TaskStatus;
	assignee: UserSummary | null;
	created_by: UserSummary;
	position: number;
	version: number;
	is_active: boolean;
	project_is_active: boolean | null;
	due_at: string | null;
	comment_count: number;
	created_at: string;
	updated_at: string;
}

export interface TaskComment {
	id: string;
	task_id: string;
	body: string;
	author: UserSummary;
	created_at: string;
	updated_at: string;
}

export interface TaskCommentsResponse {
	task_id: string;
	items: TaskComment[];
	count: number;
}

export interface TaskUpdateFields {
	title?: string;
	description?: string | null;
	status?: TaskStatus;
	assignee_id?: string | null;
	due_at?: string | null;
	position?: number;
	is_active?: boolean;
}

export type TaskUpdatePayload = TaskUpdateFields & { version: number };
export type TaskUpdateResponse = Omit<TaskDetail, "comment_count">;

export { ApiError as TaskDetailApiError } from "../../api/errors";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	return requestJson<T>(path, init);
}

export function getTask(taskId: string): Promise<TaskDetail> {
	return request<TaskDetail>(`/tasks/${encodeURIComponent(taskId)}`);
}

export function getTaskComments(taskId: string): Promise<TaskCommentsResponse> {
	return request<TaskCommentsResponse>(`/tasks/${encodeURIComponent(taskId)}/comments`);
}

export function addTaskComment(taskId: string, body: string): Promise<TaskComment> {
	return request<TaskComment>(`/tasks/${encodeURIComponent(taskId)}/comments`, {
		method: "POST",
		body: JSON.stringify({ body }),
	});
}

export function patchTask(taskId: string, payload: TaskUpdatePayload): Promise<TaskUpdateResponse> {
	return request<TaskUpdateResponse>(`/tasks/${encodeURIComponent(taskId)}`, {
		method: "PATCH",
		body: JSON.stringify(payload),
	});
}

export function patchComment(commentId: string, body: string): Promise<TaskComment> {
	return request<TaskComment>(`/comments/${encodeURIComponent(commentId)}`, {
		method: "PATCH",
		body: JSON.stringify({ body }),
	});
}

export function deleteComment(commentId: string): Promise<void> {
	return request<void>(`/comments/${encodeURIComponent(commentId)}`, { method: "DELETE" });
}

export function deleteTask(taskId: string): Promise<void> {
	return request<void>(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}
