import type { AxiosInstance } from "axios";

import { getApiClient } from "../../../api/client";
import { PROJECT_LIST_DEFAULT_PAGE, PROJECT_LIST_DEFAULT_PER_PAGE } from "../config/dashboardConfig";
import type { ProjectCreateRequest, ProjectListParams, ProjectListResponse, ProjectSummary } from "./types";

/**
 * GET /api/projects（docs/detailed_design/api/projects/01_get_projects.md）
 * 共通APIクライアント（getApiClient）を経由する。認証付与・401ハンドリング・
 * ApiErrorへの変換は client.ts のインターセプタが行うため、ここでは行わない。
 */
export async function getProjects(params: ProjectListParams = {}, client: AxiosInstance = getApiClient()): Promise<ProjectListResponse> {
	const { data } = await client.get<ProjectListResponse>("/projects", {
		params: {
			page: params.page ?? PROJECT_LIST_DEFAULT_PAGE,
			per_page: params.per_page ?? PROJECT_LIST_DEFAULT_PER_PAGE,
			include_inactive: params.include_inactive ?? false,
		},
	});
	return data;
}

/**
 * POST /api/projects（docs/detailed_design/api/projects/02_post_projects.md）
 */
export async function createProject(payload: ProjectCreateRequest, client: AxiosInstance = getApiClient()): Promise<ProjectSummary> {
	const { data } = await client.post<ProjectSummary>("/projects", payload);
	return data;
}
