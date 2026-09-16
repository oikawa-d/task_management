import { requestJson } from "../../../api/http";

export type AdminRole = "member" | "admin";
export interface AdminUser { id: string; username: string; email: string; display_name: string; role: AdminRole; is_active: boolean; created_at: string; }
export interface AdminProject { id: string; name: string; owner: { display_name: string }; member_count: number; task_counts: { todo: number; in_progress: number; done: number }; is_active: boolean; created_at: string; }
export interface PageMeta { page: number; per_page: number; total: number; total_pages: number; }
export interface AdminList<T> { items: T[]; meta: PageMeta; }
export interface UserFilters { page: number; perPage: number; q: string; role: AdminRole | ""; isActive: "" | "true" | "false"; }
export interface ProjectFilters { page: number; perPage: number; q: string; }

export function listAdminUsers(filters: UserFilters): Promise<AdminList<AdminUser>> {
	const params = new URLSearchParams({ page: String(filters.page), per_page: String(filters.perPage) });
	if (filters.q) params.set("q", filters.q);
	if (filters.role) params.set("role", filters.role);
	if (filters.isActive) params.set("is_active", String(filters.isActive === "true"));
	return requestJson(`/admin/users?${params}`);
}
export function patchAdminUserRole(userId: string, role: AdminRole): Promise<AdminUser> { return requestJson(`/admin/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role }), headers: { "Content-Type": "application/json" } }); }
export function patchAdminUserStatus(userId: string, isActive: boolean): Promise<AdminUser> { return requestJson(`/admin/users/${userId}/status`, { method: "PATCH", body: JSON.stringify({ is_active: isActive }), headers: { "Content-Type": "application/json" } }); }
export async function forceLogout(userId: string): Promise<void> { await requestJson(`/admin/users/${userId}/force-logout`, { method: "POST" }); }
export function listAdminProjects(filters: ProjectFilters): Promise<AdminList<AdminProject>> {
	const params = new URLSearchParams({ page: String(filters.page), per_page: String(filters.perPage) });
	if (filters.q) params.set("q", filters.q);
	return requestJson(`/admin/projects?${params}`);
}
export async function deleteAdminProject(projectId: string): Promise<void> { await requestJson(`/admin/projects/${projectId}`, { method: "DELETE" }); }
