import { createAuthAdapter } from "../../api/authAdapter";
import type { AuthAdapter, AuthMode, RetryableRequestConfig } from "../../api/authAdapter";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

/**
 * design doc: docs/basic_design/05_frontend.md §6.2
 * auth_modeは本来 `GET /auth/config` から実行時に取得するが、AuthProvider未実装のため
 * 既定値としてsessionモードを用いる。導入後は setAuthAdapterMode で切り替える。
 */
let authAdapter: AuthAdapter = createAuthAdapter("session");

export function setAuthAdapterMode(mode: AuthMode): void {
	authAdapter = createAuthAdapter(mode);
}

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

export class TaskDetailApiError extends Error {
	readonly status: number;
	readonly code: string | undefined;

	constructor(status: number, code?: string, message?: string) {
		super(message ?? code ?? "API_ERROR");
		this.name = "TaskDetailApiError";
		this.status = status;
		this.code = code;
	}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const headers = new Headers(init?.headers);
	headers.set("Accept", "application/json");
	if (init?.body) headers.set("Content-Type", "application/json");

	const headerEntries: Record<string, string> = {};
	headers.forEach((value, key) => {
		headerEntries[key] = value;
	});

	const config: RetryableRequestConfig = {
		method: init?.method ?? "GET",
		url: path,
		headers: headerEntries,
	};
	const attached = authAdapter.attach(config);
	const attachedHeaders = new Headers(attached.headers as Record<string, string>);

	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`, {
			...init,
			credentials: attached.withCredentials ? "include" : "same-origin",
			headers: attachedHeaders,
		});
	} catch {
		throw new TaskDetailApiError(0, "NETWORK_ERROR");
	}

	if (!response.ok) {
		let body: { code?: string; message?: string } = {};
		try {
			body = (await response.json()) as typeof body;
		} catch {
			body = {};
		}
		throw new TaskDetailApiError(response.status, body.code, body.message);
	}

	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

export function getTask(taskId: string): Promise<TaskDetail> {
	return request<TaskDetail>(`/tasks/${encodeURIComponent(taskId)}`);
}

export function getTaskComments(taskId: string): Promise<TaskCommentsResponse> {
	return request<TaskCommentsResponse>(`/tasks/${encodeURIComponent(taskId)}/comments`);
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
