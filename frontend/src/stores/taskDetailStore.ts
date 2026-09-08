import {
	deleteComment,
	deleteTask,
	getTask,
	getTaskComments,
	patchComment,
	patchTask,
	type TaskComment,
	type TaskDetail,
	type TaskDetailApiError,
	type TaskUpdateFields,
} from "../lib/api/taskDetail";

export interface TaskDetailState {
	taskId: string | null;
	task: TaskDetail | null;
	comments: TaskComment[];
	isLoading: boolean;
	isCommentsLoading: boolean;
	isSaving: boolean;
	error: TaskDetailApiError | Error | null;
	commentsError: TaskDetailApiError | Error | null;
	notFound: boolean;
	conflictBannerVisible: boolean;
	closeRequested: boolean;
	boardRefreshToken: number;
}

const INITIAL_STATE: TaskDetailState = {
	taskId: null,
	task: null,
	comments: [],
	isLoading: false,
	isCommentsLoading: false,
	isSaving: false,
	error: null,
	commentsError: null,
	notFound: false,
	conflictBannerVisible: false,
	closeRequested: false,
	boardRefreshToken: 0,
};

type Listener = () => void;

function isApiError(reason: unknown): reason is TaskDetailApiError {
	return reason instanceof Error && "status" in reason && "code" in reason;
}

function isNotFound(reason: unknown): boolean {
	return isApiError(reason) && (reason.status === 404 || reason.code === "NOT_FOUND");
}

function asError(reason: unknown): TaskDetailApiError | Error {
	return reason instanceof Error ? reason : new Error("API_ERROR");
}

class TaskDetailStore {
	private state = INITIAL_STATE;
	private listeners = new Set<Listener>();
	private requestId = 0;

	getSnapshot = (): TaskDetailState => this.state;

	subscribe = (listener: Listener): (() => void) => {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	};

	private setState(update: Partial<TaskDetailState>) {
		this.state = { ...this.state, ...update };
		this.listeners.forEach((listener) => listener());
	}

	reset() {
		this.requestId += 1;
		this.state = INITIAL_STATE;
		this.listeners.forEach((listener) => listener());
	}

	async open(taskId: string): Promise<void> {
		const requestId = ++this.requestId;
		this.setState({
			taskId,
			task: null,
			comments: [],
			isLoading: true,
			isCommentsLoading: true,
			isSaving: false,
			error: null,
			commentsError: null,
			notFound: false,
			conflictBannerVisible: false,
			closeRequested: false,
		});

		const [taskResult, commentsResult] = await Promise.allSettled([getTask(taskId), getTaskComments(taskId)]);
		if (requestId !== this.requestId) return;

		const taskMissing = taskResult.status === "rejected" && isNotFound(taskResult.reason);
		const commentsMissing = commentsResult.status === "rejected" && isNotFound(commentsResult.reason);
		this.setState({
			task: taskResult.status === "fulfilled" ? taskResult.value : null,
			comments: commentsResult.status === "fulfilled" ? commentsResult.value.items : [],
			isLoading: false,
			isCommentsLoading: false,
			error: taskResult.status === "rejected" ? asError(taskResult.reason) : null,
			commentsError: commentsResult.status === "rejected" ? asError(commentsResult.reason) : null,
			notFound: taskMissing || commentsMissing,
			closeRequested: false,
		});
	}

	private async refreshTask(taskId: string, keepConflict: boolean): Promise<void> {
		try {
			const task = await getTask(taskId);
			if (this.state.taskId !== taskId) return;
			this.setState({ task, error: null, notFound: false, conflictBannerVisible: keepConflict });
		} catch (reason: unknown) {
			if (this.state.taskId !== taskId) return;
			this.setState({ error: asError(reason), notFound: isNotFound(reason), closeRequested: isNotFound(reason) });
		}
	}

	async updateTask(taskId: string, fields: TaskUpdateFields): Promise<void> {
		if (this.state.taskId !== taskId || !this.state.task) return;
		const version = this.state.task.version;
		this.setState({ isSaving: true, error: null });
		try {
			const updatedTask = await patchTask(taskId, { ...fields, version });
			if (this.state.taskId !== taskId) return;
			const task = { ...this.state.task, ...updatedTask };
			this.setState({ task, isSaving: false, conflictBannerVisible: false, boardRefreshToken: this.state.boardRefreshToken + 1 });
		} catch (reason: unknown) {
			if (this.state.taskId !== taskId) return;
			if (isApiError(reason) && reason.status === 409 && reason.code === "TASK_CONFLICT") {
				await this.refreshTask(taskId, true);
				this.setState({ isSaving: false });
				return;
			}
			this.setState({
				isSaving: false,
				error: asError(reason),
				closeRequested: isNotFound(reason),
				notFound: isNotFound(reason),
			});
		}
	}

	async updateComment(commentId: string, body: string): Promise<void> {
		const taskId = this.state.taskId;
		this.setState({ isSaving: true, error: null });
		try {
			const updated = await patchComment(commentId, body);
			if (this.state.taskId !== taskId) return;
			this.setState({
				comments: this.state.comments.map((comment) => (comment.id === commentId ? updated : comment)),
				isSaving: false,
			});
		} catch (reason: unknown) {
			if (this.state.taskId !== taskId) return;
			this.setState({ isSaving: false, error: asError(reason) });
			if (isNotFound(reason) && this.state.taskId) await this.refreshComments(this.state.taskId);
		}
	}

	async removeComment(taskId: string, commentId: string): Promise<void> {
		this.setState({ isSaving: true, error: null });
		try {
			await deleteComment(commentId);
			if (this.state.taskId !== taskId) return;
			const wasPresent = this.state.comments.some((comment) => comment.id === commentId);
			const task = this.state.task && wasPresent
				? { ...this.state.task, comment_count: Math.max(0, this.state.task.comment_count - 1) }
				: this.state.task;
			this.setState({ task, comments: this.state.comments.filter((comment) => comment.id !== commentId), isSaving: false });
		} catch (reason: unknown) {
			if (this.state.taskId !== taskId) return;
			this.setState({ isSaving: false, error: asError(reason) });
			if (isNotFound(reason)) await this.refreshComments(taskId);
		}
	}

	async removeTask(taskId: string): Promise<void> {
		this.setState({ isSaving: true, error: null });
		try {
			await deleteTask(taskId);
			if (this.state.taskId !== taskId) return;
			this.setState({ isSaving: false, closeRequested: true, boardRefreshToken: this.state.boardRefreshToken + 1 });
		} catch (reason: unknown) {
			if (this.state.taskId !== taskId) return;
			const missing = isNotFound(reason);
			this.setState({ isSaving: false, error: missing ? null : asError(reason), closeRequested: missing, notFound: missing });
		}
	}

	private async refreshComments(taskId: string): Promise<void> {
		if (this.state.taskId !== taskId) return;
		this.setState({ isCommentsLoading: true });
		try {
			const response = await getTaskComments(taskId);
			if (this.state.taskId === taskId) {
				this.setState({ comments: response.items, isCommentsLoading: false, commentsError: null });
			}
		} catch (reason: unknown) {
			if (this.state.taskId === taskId) this.setState({ isCommentsLoading: false, commentsError: asError(reason) });
		}
	}

	requestClose() {
		this.setState({ closeRequested: true });
	}

	acknowledgeClose() {
		this.setState({ closeRequested: false });
	}
}

export const taskDetailStore = new TaskDetailStore();
