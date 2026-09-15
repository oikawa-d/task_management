import { useQuery } from "@tanstack/react-query";

import { getProjectMembers } from "../api";

export function useProjectMembers(projectId: string) {
	const query = useQuery({
		queryKey: ["project-members", projectId],
		queryFn: () => getProjectMembers(projectId),
		enabled: Boolean(projectId),
	});

	return {
		members: query.data?.items ?? [],
		isLoading: query.isLoading,
		error: query.error instanceof Error ? query.error : null,
	};
}
