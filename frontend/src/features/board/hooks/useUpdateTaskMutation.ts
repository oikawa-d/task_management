import { useMutation, useQueryClient } from "@tanstack/react-query";

import { BoardApiError, updateTask } from "../api";
import type { BoardResponse, TaskStatus } from "../types";

export interface UpdateTaskVariables {
	taskId: string;
	status: TaskStatus;
	position: number;
	version: number;
}

function moveTask(board: BoardResponse, variables: UpdateTaskVariables): BoardResponse {
	const columns = Object.fromEntries(
		Object.entries(board.columns).map(([status, tasks]) => [status, tasks.map((task) => ({ ...task }))]),
	) as BoardResponse["columns"];
	let moved = null;
	for (const tasks of Object.values(columns)) {
		const index = tasks.findIndex((task) => task.id === variables.taskId);
		if (index >= 0) {
			moved = tasks.splice(index, 1)[0];
			break;
		}
	}
	if (!moved) return board;
	const target = columns[variables.status];
	target.splice(Math.min(variables.position, target.length), 0, { ...moved, status: variables.status });
	for (const tasks of Object.values(columns)) {
		tasks.forEach((task, index) => {
			task.position = index;
		});
	}
	return { ...board, columns };
}

export function useUpdateTaskMutation(
	projectId: string,
	onConflict?: () => void,
	onFailure?: () => void,
) {
	const queryClient = useQueryClient();
	return useMutation({
		mutationKey: ["updateTask", projectId],
		mutationFn: ({ taskId, status, position, version }: UpdateTaskVariables) =>
			updateTask(taskId, { status, position, version }),
		onMutate: async (variables) => {
			await queryClient.cancelQueries({ queryKey: ["board", projectId] });
			const previous = queryClient.getQueryData<BoardResponse>(["board", projectId]);
			if (previous) queryClient.setQueryData(["board", projectId], moveTask(previous, variables));
			return { previous };
		},
		onError: (error, _variables, context) => {
			if (error instanceof BoardApiError && error.code === "TASK_CONFLICT") {
				onConflict?.();
				void queryClient.invalidateQueries({ queryKey: ["board", projectId] });
				return;
			}
			if (context?.previous) queryClient.setQueryData(["board", projectId], context.previous);
			onFailure?.();
		},
		onSettled: (_data, error) => {
			if (!error) void queryClient.invalidateQueries({ queryKey: ["board", projectId] });
		},
	});
}

export { moveTask };
