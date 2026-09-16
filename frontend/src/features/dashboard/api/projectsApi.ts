import { requestJson } from "../../../api/http";
import { PROJECT_LIST_DEFAULT_PAGE, PROJECT_LIST_DEFAULT_PER_PAGE } from "../config/dashboardConfig";
import type { CalendarTask, CalendarTaskParams, ProjectCreateRequest, ProjectListParams, ProjectListResponse, ProjectSummary } from "./types";

/**
 * GET /api/projects（docs/detailed_design/api/projects/01_get_projects.md）
 * fetchWithAuthを経由し、認証付与・401ハンドリング・エラー変換を共通化する。
 */
export function getProjects(params: ProjectListParams = {}): Promise<ProjectListResponse> {
	const query = new URLSearchParams({
		page: String(params.page ?? PROJECT_LIST_DEFAULT_PAGE),
		per_page: String(params.per_page ?? PROJECT_LIST_DEFAULT_PER_PAGE),
		include_inactive: String(params.include_inactive ?? false),
	});
	return requestJson(`/projects?${query}`);
}

/**
 * POST /api/projects（docs/detailed_design/api/projects/02_post_projects.md）
 */
export function createProject(payload: ProjectCreateRequest): Promise<ProjectSummary> {
	return requestJson("/projects", { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
}

export async function getCalendarTasks(
	params: CalendarTaskParams,
): Promise<CalendarTask[]> {
	const query = new URLSearchParams({
		from: params.from,
		to: params.to,
		scope: params.scope,
		...(params.project_id ? { project_id: params.project_id } : {}),
	});
	return requestJson<CalendarTask[]>(`/tasks/calendar?${query}`).then((data) => Array.isArray(data) ? data : []);
}
