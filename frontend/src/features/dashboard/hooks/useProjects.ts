import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getProjects } from "../api/projectsApi";
import type { ProjectListParams, ProjectListResponse } from "../api/types";
import { PROJECT_LIST_DEFAULT_PAGE, PROJECT_LIST_DEFAULT_PER_PAGE, PROJECTS_QUERY_KEY } from "../config/dashboardConfig";

/**
 * docs/detailed_design/screen/06_dashboard.md §5
 * queryKey: ['projects', { page, perPage }]
 */
export function projectsQueryKey(params: ProjectListParams) {
	return [PROJECTS_QUERY_KEY, { page: params.page ?? PROJECT_LIST_DEFAULT_PAGE, perPage: params.per_page ?? PROJECT_LIST_DEFAULT_PER_PAGE }] as const;
}

export function useProjects(params: ProjectListParams = {}): UseQueryResult<ProjectListResponse> {
	return useQuery({
		queryKey: projectsQueryKey(params),
		queryFn: () => getProjects(params),
	});
}
