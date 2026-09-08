export const ROUTES = {
	ROOT: "/",
	LOGIN: "/login",
	DASHBOARD: "/dashboard",
	SETTINGS: "/settings",
	ADMIN_USERS: "/admin/users",
	PROJECT: (projectId: string) => `/projects/${projectId}`,
} as const;
