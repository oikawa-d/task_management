import { useQuery } from "@tanstack/react-query";

import { getProjectTasks } from "../api";
import type { BoardResponse } from "../types";

const EMPTY_BOARD: BoardResponse = {
	project_id: "",
	project_is_active: true,
	columns: { todo: [], in_progress: [], done: [] },
};

export function useBoard(projectId: string | undefined) {
	const query = useQuery({
		queryKey: ["board", projectId],
		queryFn: () => getProjectTasks(projectId as string),
		enabled: Boolean(projectId),
	});

	return {
		board: query.data ?? EMPTY_BOARD,
		isLoading: Boolean(projectId) && query.isLoading,
		error: query.error instanceof Error ? query.error : null,
		refetch: query.refetch,
	};
}
