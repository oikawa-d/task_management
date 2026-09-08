export type AdminUserRole = "member" | "admin";

export interface AdminUserSummary {
	id: string;
	username: string;
	email: string;
	displayName: string;
	role: AdminUserRole;
	isActive: boolean;
}
