export const ROUTES = {
	ROOT: "/",
	PROJECT_PATTERN: "/projects/:projectId",
	TASK_PATTERN: "/projects/:projectId/tasks/:taskId",
	PROJECT: (projectId: string) => `/projects/${projectId}`,
	TASK: (projectId: string, taskId: string) => `/projects/${projectId}/tasks/${taskId}`,
} as const;
