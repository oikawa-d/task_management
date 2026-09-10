/**
 * `GET /api/projects` / `POST /api/projects` のレスポンス契約。
 * docs/detailed_design/api/projects/01_get_projects.md §2.2
 * docs/detailed_design/api/projects/02_post_projects.md §2.2
 */

export interface ProjectOwner {
	id: string;
	username: string;
	display_name: string;
}

export interface ProjectTaskCounts {
	todo: number;
	in_progress: number;
	done: number;
}

export interface ProjectSummary {
	id: string;
	name: string;
	description: string | null;
	owner: ProjectOwner;
	member_count: number;
	task_counts: ProjectTaskCounts;
	is_owner: boolean;
	is_active: boolean;
	start_at: string | null;
	end_at: string | null;
	created_at: string;
}

export interface ProjectListMeta {
	page: number;
	per_page: number;
	total: number;
	total_pages: number;
}

export interface ProjectListResponse {
	items: ProjectSummary[];
	meta: ProjectListMeta;
}

export interface ProjectListParams {
	page?: number;
	per_page?: number;
	include_inactive?: boolean;
}

/** docs/detailed_design/api/projects/02_post_projects.md §2.1 */
export interface ProjectCreateRequest {
	name: string;
	description?: string | null;
	start_at?: string | null;
	end_at?: string | null;
}
