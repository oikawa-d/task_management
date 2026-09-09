import { fetchWithAuth } from "../../api/authAdapter/client";
import type { BoardResponse } from "./types";

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

async function getJson<T>(path: string): Promise<T> {
	const response = await fetchWithAuth(`${API_BASE_URL}${path}`, {
		headers: { Accept: "application/json" },
	}, API_BASE_URL);
	if (!response.ok) {
		let code: string | undefined;
		try {
			const body = (await response.json()) as { code?: string };
			code = body.code;
		} catch {
			code = undefined;
		}
		throw new BoardApiError(response.status, code);
	}
	return response.json() as Promise<T>;
}

export function getProjectTasks(projectId: string): Promise<BoardResponse> {
	return getJson<BoardResponse>(`/projects/${projectId}/tasks`);
}
