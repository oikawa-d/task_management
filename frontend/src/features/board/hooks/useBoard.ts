import { useEffect, useState } from "react";

import { getProjectTasks } from "../api";
import type { BoardResponse } from "../types";

const EMPTY_BOARD: BoardResponse = {
	columns: { todo: [], in_progress: [], done: [] },
};

export function useBoard(projectId: string | undefined) {
	const [board, setBoard] = useState<BoardResponse>(EMPTY_BOARD);
	const [isLoading, setIsLoading] = useState(Boolean(projectId));
	const [error, setError] = useState<Error | null>(null);

	useEffect(() => {
		if (!projectId) {
			return;
		}
		let active = true;
		setIsLoading(true);
		setError(null);
		void getProjectTasks(projectId)
			.then((response) => {
				if (active) setBoard(response);
			})
			.catch((reason: unknown) => {
				if (active) setError(reason instanceof Error ? reason : new Error("API_ERROR"));
			})
			.finally(() => {
				if (active) setIsLoading(false);
			});
		return () => {
			active = false;
		};
	}, [projectId]);

	return { board, isLoading, error };
}
