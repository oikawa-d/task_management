import { useEffect, useState } from "react";

import { useAuthStore } from "../../../auth/authStore";
import type { AdminProject, AdminRole, AdminUser, PageMeta, ProjectFilters, UserFilters } from "../api/adminApi";
import { ProjectTable } from "../components/ProjectTable";
import { UserTable } from "../components/UserTable";
import { useAdminProjects, useDeleteAdminProject } from "../hooks/useAdminProjects";
import { useAdminUsers, useChangeRole, useChangeStatus, useForceLogout } from "../hooks/useAdminUsers";

type DialogAction = { kind: "role" | "status" | "logout" | "project"; user?: AdminUser; project?: AdminProject; role?: AdminRole; active?: boolean };
const DEFAULT_USER_FILTERS: UserFilters = { page: 1, perPage: 20, q: "", role: "", isActive: "" };
const DEFAULT_PROJECT_FILTERS: ProjectFilters = { page: 1, perPage: 20, q: "" };

function Pagination({ label, meta, onPageChange }: { label: string; meta?: PageMeta; onPageChange: (page: number) => void }) {
	if (!meta || meta.total_pages <= 1) return null;
	return <nav aria-label={label}><button type="button" disabled={meta.page <= 1} onClick={() => onPageChange(meta.page - 1)}>前へ</button>{Array.from({ length: meta.total_pages }, (_, index) => index + 1).map((page) => <button key={page} type="button" aria-current={page === meta.page ? "page" : undefined} onClick={() => onPageChange(page)}>{page}</button>)}<button type="button" disabled={meta.page >= meta.total_pages} onClick={() => onPageChange(meta.page + 1)}>次へ</button></nav>;
}

export function AdminUsersPage() {
	const currentUserId = useAuthStore((state) => state.user?.id);
	const [tab, setTab] = useState<"users" | "projects">("users");
	const [filters, setFilters] = useState(DEFAULT_USER_FILTERS);
	const [projectFilters, setProjectFilters] = useState(DEFAULT_PROJECT_FILTERS);
	const [userSearch, setUserSearch] = useState("");
	const [projectSearch, setProjectSearch] = useState("");
	const [dialog, setDialog] = useState<DialogAction | null>(null);
	const [message, setMessage] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const users = useAdminUsers(filters, tab === "users");
	const projects = useAdminProjects(projectFilters, tab === "projects");
	const roleMutation = useChangeRole();
	const statusMutation = useChangeStatus();
	const logoutMutation = useForceLogout();
	const deleteMutation = useDeleteAdminProject();

	useEffect(() => {
		const timer = window.setTimeout(() => setFilters((current) => ({ ...current, q: userSearch, page: 1 })), 300);
		return () => window.clearTimeout(timer);
	}, [userSearch]);
	useEffect(() => {
		const timer = window.setTimeout(() => setProjectFilters((current) => ({ ...current, q: projectSearch, page: 1 })), 300);
		return () => window.clearTimeout(timer);
	}, [projectSearch]);

	const runAction = async () => {
		if (!dialog) return;
		setError(null);
		try {
			if (dialog.kind === "role" && dialog.user && dialog.role) await roleMutation.mutateAsync({ userId: dialog.user.id, role: dialog.role });
			if (dialog.kind === "status" && dialog.user && dialog.active !== undefined) await statusMutation.mutateAsync({ userId: dialog.user.id, isActive: dialog.active });
			if (dialog.kind === "logout" && dialog.user) await logoutMutation.mutateAsync(dialog.user.id);
			if (dialog.kind === "project" && dialog.project) await deleteMutation.mutateAsync(dialog.project.id);
			setDialog(null);
			setMessage("操作が完了しました。");
		} catch (reason) {
			setError(reason instanceof Error ? reason.message : "操作に失敗しました。");
		}
	};
	const updateUserFilters = (next: Partial<UserFilters>) => setFilters((current) => ({ ...current, ...next, page: next.page ?? 1 }));
	const updateProjectFilters = (next: Partial<ProjectFilters>) => setProjectFilters((current) => ({ ...current, ...next, page: next.page ?? 1 }));

	return <section>
		<h1>管理者画面</h1>
		<div role="tablist" aria-label="管理対象"><button type="button" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>ユーザー</button><button type="button" role="tab" aria-selected={tab === "projects"} onClick={() => setTab("projects")}>プロジェクト</button></div>
		{message ? <p role="status">{message}</p> : null}{error ? <p role="alert">{error}</p> : null}
		{tab === "users" ? <>
			<label>検索<input value={userSearch} onChange={(event) => setUserSearch(event.target.value)} /></label>
			<label>権限<select aria-label="roleフィルタ" value={filters.role} onChange={(event) => updateUserFilters({ role: event.target.value as UserFilters["role"] })}><option value="">すべて</option><option value="member">member</option><option value="admin">admin</option></select></label>
			<label>状態<select aria-label="is_activeフィルタ" value={filters.isActive} onChange={(event) => updateUserFilters({ isActive: event.target.value as UserFilters["isActive"] })}><option value="">すべて</option><option value="true">有効</option><option value="false">無効</option></select></label>
			{users.isLoading ? <p role="status">読み込み中...</p> : users.isError ? <button type="button" onClick={() => void users.refetch()}>再試行</button> : <><UserTable items={users.data?.items ?? []} currentUserId={currentUserId} onRoleChange={(user, role) => setDialog({ kind: "role", user, role })} onStatusChange={(user, active) => active ? void statusMutation.mutate({ userId: user.id, isActive: true }) : setDialog({ kind: "status", user, active })} onForceLogout={(user) => setDialog({ kind: "logout", user })} /><Pagination label="ユーザーページ" meta={users.data?.meta} onPageChange={(page) => updateUserFilters({ page })} /></>}
		</> : <>
			<label>検索<input value={projectSearch} onChange={(event) => setProjectSearch(event.target.value)} /></label>
			{projects.isLoading ? <p role="status">読み込み中...</p> : projects.isError ? <button type="button" onClick={() => void projects.refetch()}>再試行</button> : <><ProjectTable items={projects.data?.items ?? []} onDelete={(project) => setDialog({ kind: "project", project })} /><Pagination label="プロジェクトページ" meta={projects.data?.meta} onPageChange={(page) => updateProjectFilters({ page })} /></>}
		</>}
		{dialog ? <div role="alertdialog" aria-label="操作確認"><p>この操作を実行しますか？</p><button type="button" onClick={() => void runAction()}>確定</button><button type="button" onClick={() => { setDialog(null); setError(null); }}>キャンセル</button></div> : null}
	</section>;
}
