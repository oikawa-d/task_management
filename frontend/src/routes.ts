export const ROUTES = {
	ROOT: "/",
	LOGIN: "/login",
	REGISTER: "/register",
	PASSWORD_FORGOT: "/password/forgot",
	DASHBOARD: "/dashboard",
	SETTINGS: "/settings",
	ADMIN_USERS: "/admin/users",
	PROJECT_PATTERN: "/projects/:projectId",
	TASK_PATTERN: "/projects/:projectId/tasks/:taskId",
	PROJECT: (projectId: string) => `/projects/${projectId}`,
	TASK: (projectId: string, taskId: string) => `/projects/${projectId}/tasks/${taskId}`,
} as const;
