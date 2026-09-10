import { useEffect, useRef, useSyncExternalStore } from "react";

import type { TaskUpdateFields } from "../../../lib/api/taskDetail";
import { taskDetailStore } from "../../../stores/taskDetailStore";

export interface UseTaskDetailOptions {
	onClose?: () => void;
}

export function useTaskDetail(taskId: string | undefined, options: UseTaskDetailOptions = {}) {
	const state = useSyncExternalStore(taskDetailStore.subscribe, taskDetailStore.getSnapshot, taskDetailStore.getSnapshot);
	const onCloseRef = useRef(options.onClose);
	onCloseRef.current = options.onClose;

	useEffect(() => {
		if (taskId) void taskDetailStore.open(taskId);
	}, [taskId]);

	useEffect(() => {
		if (state.taskId !== taskId || !state.closeRequested) return;
		if (!onCloseRef.current) return;
		taskDetailStore.acknowledgeClose();
		onCloseRef.current?.();
	}, [state.closeRequested, state.taskId, taskId]);

	return {
		...state,
		updateTask: (fields: TaskUpdateFields) => (taskId ? taskDetailStore.updateTask(taskId, fields) : Promise.resolve()),
		updateComment: taskDetailStore.updateComment.bind(taskDetailStore),
		removeComment: taskDetailStore.removeComment.bind(taskDetailStore),
		removeTask: (id = taskId) => (id ? taskDetailStore.removeTask(id) : Promise.resolve()),
		refresh: () => (taskId ? taskDetailStore.open(taskId) : Promise.resolve()),
	};
}
