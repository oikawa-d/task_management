import { useEffect, useRef, useSyncExternalStore } from "react";

import type { TaskUpdateFields } from "../../../lib/api/taskDetail";
import { taskDetailStore } from "../../../stores/taskDetailStore";

export interface UseTaskDetailOptions {
	onClose?: () => void;
	onBoardRefresh?: () => void;
}

export function useTaskDetail(taskId: string | undefined, options: UseTaskDetailOptions = {}) {
	const state = useSyncExternalStore(taskDetailStore.subscribe, taskDetailStore.getSnapshot, taskDetailStore.getSnapshot);
	const onCloseRef = useRef(options.onClose);
	const onBoardRefreshRef = useRef(options.onBoardRefresh);
	const previousBoardRefreshToken = useRef(state.boardRefreshToken);
	onCloseRef.current = options.onClose;
	onBoardRefreshRef.current = options.onBoardRefresh;

	useEffect(() => {
		if (taskId) void taskDetailStore.open(taskId);
	}, [taskId]);

	useEffect(() => {
		if (state.taskId !== taskId || !state.closeRequested) return;
		if (!onCloseRef.current) return;
		taskDetailStore.acknowledgeClose();
		onCloseRef.current?.();
	}, [state.closeRequested, state.taskId, taskId]);

	useEffect(() => {
		if (previousBoardRefreshToken.current !== state.boardRefreshToken) {
			previousBoardRefreshToken.current = state.boardRefreshToken;
			onBoardRefreshRef.current?.();
		}
	}, [state.boardRefreshToken]);

	return {
		...state,
		updateTask: (fields: TaskUpdateFields) => (taskId ? taskDetailStore.updateTask(taskId, fields) : Promise.resolve()),
		updateComment: taskDetailStore.updateComment.bind(taskDetailStore),
		removeComment: (commentId: string) => (
			taskId ? taskDetailStore.removeComment(taskId, commentId) : Promise.resolve()
		),
		removeTask: (id = taskId) => (id ? taskDetailStore.removeTask(id) : Promise.resolve()),
		refresh: () => (taskId ? taskDetailStore.open(taskId) : Promise.resolve()),
	};
}
