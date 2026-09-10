import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createProject } from "../api/projectsApi";
import type { ProjectCreateRequest, ProjectSummary } from "../api/types";
import { CREATE_PROJECT_MUTATION_KEY, PROJECTS_QUERY_KEY } from "../config/dashboardConfig";

/**
 * docs/detailed_design/screen/06_dashboard.md §4 No.2 / §7.2
 * 成功時は ['projects'] を invalidate して一覧を再取得する。
 */
export function useCreateProject(): UseMutationResult<ProjectSummary, unknown, ProjectCreateRequest> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationKey: [CREATE_PROJECT_MUTATION_KEY],
		mutationFn: (payload: ProjectCreateRequest) => createProject(payload),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: [PROJECTS_QUERY_KEY] });
		},
	});
}
