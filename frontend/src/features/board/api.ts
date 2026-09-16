import { requestJson as request } from "../../api/http";
import type { BoardResponse, BoardTask, ProjectMemberListResponse, TaskStatus } from "./types";

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
	return request<T>(path, init);
}

export { ApiError as BoardApiError } from "../../api/errors";

export function getProjectTasks(projectId: string): Promise<BoardResponse> {
	return requestJson<BoardResponse>(`/projects/${projectId}/tasks`);
}

export function getProjectMembers(projectId: string): Promise<ProjectMemberListResponse> {
	return requestJson<ProjectMemberListResponse>(`/projects/${projectId}/members`);
}

export interface UpdateTaskRequest {
	version: number;
	status: TaskStatus;
	position: number;
}

export function updateTask(taskId: string, payload: UpdateTaskRequest): Promise<BoardTask> {
	return requestJson<BoardTask>(`/tasks/${taskId}`, {
		method: "PATCH",
		headers: { Accept: "application/json", "Content-Type": "application/json" },
		body: JSON.stringify(payload),
	});
}
