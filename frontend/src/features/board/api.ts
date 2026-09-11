import { fetchWithAuth } from "../../api/authAdapter/client";
import type { BoardResponse, BoardTask, TaskStatus } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export class BoardApiError extends Error {
	constructor(
		readonly status: number,
		readonly code: string | undefined,
	) {
		super(code ?? "API_ERROR");
		this.name = "BoardApiError";
	}
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
	const response = await fetchWithAuth(`${API_BASE_URL}${path}`, {
		...init,
		headers: { Accept: "application/json", ...init.headers },
	}, API_BASE_URL);
	if (!response.ok) {
		let code: string | undefined;
		try {
			const body = (await response.json()) as { code?: string; error?: { code?: string } };
			code = body.error?.code ?? body.code;
		} catch {
			code = undefined;
		}
		throw new BoardApiError(response.status, code);
	}
	return response.json() as Promise<T>;
}

export function getProjectTasks(projectId: string): Promise<BoardResponse> {
	return requestJson<BoardResponse>(`/projects/${projectId}/tasks`);
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
