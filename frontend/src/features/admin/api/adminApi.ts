import type { AxiosInstance } from "axios";

import { getApiClient } from "../../../api/client";

export type AdminRole = "member" | "admin";
export interface AdminUser { id: string; username: string; email: string; display_name: string; role: AdminRole; is_active: boolean; created_at: string; }
export interface AdminProject { id: string; name: string; owner: { display_name: string }; member_count: number; task_counts: { todo: number; in_progress: number; done: number }; is_active: boolean; created_at: string; }
export interface PageMeta { page: number; per_page: number; total: number; total_pages: number; }
export interface AdminList<T> { items: T[]; meta: PageMeta; }
export interface UserFilters { page: number; perPage: number; q: string; role: AdminRole | ""; isActive: "" | "true" | "false"; }
export interface ProjectFilters { page: number; perPage: number; q: string; }

export async function listAdminUsers(filters: UserFilters, client: AxiosInstance = getApiClient()): Promise<AdminList<AdminUser>> {
	const { data } = await client.get<AdminList<AdminUser>>("/admin/users", { params: { page: filters.page, per_page: filters.perPage, q: filters.q || undefined, role: filters.role || undefined, is_active: filters.isActive === "" ? undefined : filters.isActive === "true" } });
	return data;
}
export async function patchAdminUserRole(userId: string, role: AdminRole, client: AxiosInstance = getApiClient()) { return (await client.patch<AdminUser>(`/admin/users/${userId}/role`, { role })).data; }
export async function patchAdminUserStatus(userId: string, isActive: boolean, client: AxiosInstance = getApiClient()) { return (await client.patch<AdminUser>(`/admin/users/${userId}/status`, { is_active: isActive })).data; }
export async function forceLogout(userId: string, client: AxiosInstance = getApiClient()) { await client.post(`/admin/users/${userId}/force-logout`); }
export async function listAdminProjects(filters: ProjectFilters, client: AxiosInstance = getApiClient()): Promise<AdminList<AdminProject>> { const { data } = await client.get<AdminList<AdminProject>>("/admin/projects", { params: { page: filters.page, per_page: filters.perPage, q: filters.q || undefined } }); return data; }
export async function deleteAdminProject(projectId: string, client: AxiosInstance = getApiClient()) { await client.delete(`/admin/projects/${projectId}`); }
