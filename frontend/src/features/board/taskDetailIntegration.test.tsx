import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthAdapter, setAuthAdapterMode } from "../../api/authAdapter/client";
import { useAuthStore } from "../../auth/authStore";
import { ROUTES } from "../../routes";
import { taskDetailStore } from "../../stores/taskDetailStore";
import { BoardPage } from "./BoardPage";

const task = {
	id: "task-1",
	project_id: "project-1",
	title: "結合テスト対象",
	description: "詳細説明",
	status: "todo" as const,
	assignee: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	created_by: { id: "user-1", username: "taro", display_name: "山田 太郎" },
	position: 0,
	version: 1,
	is_active: true,
	project_is_active: true,
	due_at: "2026-09-09T14:59:00Z",
	comment_count: 1,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

const initialComment = {
	id: "comment-1",
	task_id: task.id,
	body: "既存コメント",
	author: task.created_by,
	created_at: "2026-09-01T10:00:00Z",
	updated_at: "2026-09-01T10:00:00Z",
};

type MockTask = Omit<typeof task, "assignee"> & { assignee: typeof task.assignee | null };

function jsonResponse(status: number, body?: unknown) {
	return Promise.resolve({
		ok: status < 400,
		status,
		headers: new Headers(),
		json: () => Promise.resolve(body),
	});
}

function createApiMock(options: { taskStatus?: number; commentsStatus?: number } = {}) {
	let currentTask: MockTask = { ...task };
	let comments = [initialComment];
	let conflict = false;
	let failTaskUpdate = false;
	let deleted = false;
	const projectMembers = [
		{ user_id: "user-1", username: "taro", display_name: "山田 太郎", role: "member", is_owner: true, is_active: true, joined_at: "2026-09-01T00:00:00Z" },
		{ user_id: "user-2", username: "hanako", display_name: "佐藤 花子", role: "member", is_owner: false, is_active: false, joined_at: "2026-09-01T00:00:00Z" },
		{ user_id: "user-3", username: "ichiro", display_name: "鈴木 一郎", role: "member", is_owner: false, is_active: true, joined_at: "2026-09-01T00:00:00Z" },
	];
	const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
		const path = new URL(String(input), "http://localhost").pathname;
		const method = init?.method ?? "GET";
		if (path === "/api/projects/project-1/tasks") {
			return jsonResponse(200, {
				project_id: "project-1",
				project_is_active: true,
				columns: { todo: deleted ? [] : [currentTask], in_progress: [], done: [] },
			});
		}
		if (path === "/api/projects/project-1/members") {
			return jsonResponse(200, {
				items: projectMembers,
				meta: { total: 3 },
			});
		}
		if (path.startsWith("/api/tasks/") && method === "GET" && !path.endsWith("/comments")) {
			if (options.taskStatus) return jsonResponse(options.taskStatus, { code: "NOT_FOUND" });
			return jsonResponse(200, currentTask);
		}
		if (path.startsWith("/api/tasks/") && path.endsWith("/comments") && method === "GET") {
			if (options.commentsStatus) return jsonResponse(options.commentsStatus, { code: "NOT_FOUND" });
			return jsonResponse(200, { task_id: task.id, items: comments, count: comments.length });
		}
		if (path.endsWith("/task-1") && method === "PATCH") {
			if (conflict) {
				conflict = false;
				currentTask = { ...currentTask, title: "他ユーザーの最新タイトル", version: currentTask.version + 1 };
				return jsonResponse(409, { code: "TASK_CONFLICT" });
			}
			if (failTaskUpdate) return jsonResponse(503, { code: "SERVICE_UNAVAILABLE" });
			const payload = JSON.parse(String(init?.body)) as Partial<typeof task> & { version: number; assignee_id?: string | null };
			currentTask = { ...currentTask, ...payload, version: currentTask.version + 1 };
			if (payload.assignee_id === "user-3") currentTask.assignee = { id: "user-3", username: "ichiro", display_name: "鈴木 一郎" };
			if (payload.assignee_id === null) currentTask.assignee = null;
			return jsonResponse(200, currentTask);
		}
		if (path.endsWith("/task-1") && method === "DELETE") {
			deleted = true;
			return jsonResponse(204);
		}
		if (path.endsWith("/task-1/comments") && method === "POST") {
			const payload = JSON.parse(String(init?.body)) as { body: string };
			const added = { ...initialComment, id: "comment-2", body: payload.body };
			comments = [...comments, added];
			currentTask = { ...currentTask, comment_count: comments.length };
			return jsonResponse(201, added);
		}
		if (path === "/api/comments/comment-1" && method === "PATCH") {
			const payload = JSON.parse(String(init?.body)) as { body: string };
			comments = comments.map((item) => ({ ...item, body: payload.body }));
			return jsonResponse(200, comments[0]);
		}
		if (path === "/api/comments/comment-1" && method === "DELETE") {
			comments = comments.filter((item) => item.id !== "comment-1");
			currentTask = { ...currentTask, comment_count: comments.length };
			return jsonResponse(204);
		}
		throw new Error(`unexpected request: ${method} ${path}`);
	});
	return { fetchMock, setConflict: () => { conflict = true; }, setTaskFailure: () => { failTaskUpdate = true; } };
}

function renderBoard(
	initialEntry: string,
	fetchMock: ReturnType<typeof createApiMock>["fetchMock"],
	initialEntries = [initialEntry],
) {
	const router = createMemoryRouter(
		[
			{ path: ROUTES.PROJECT_PATTERN, element: <BoardPage /> },
			{ path: ROUTES.TASK_PATTERN, element: <BoardPage /> },
		],
		{ initialEntries, initialIndex: initialEntries.length - 1 },
	);
	vi.stubGlobal("fetch", fetchMock);
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return {
		router,
		...render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>),
	};
}

describe("タスク詳細モーダルの結合テスト（Issue #433 / 親phase #164）", () => {
	beforeEach(() => {
		setAuthAdapterMode("session");
		useAuthStore.setState({ status: "authenticated", user: { id: "user-1", role: "member" } });
	});

	afterEach(() => {
		clearAuthAdapter();
		useAuthStore.getState().reset();
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it("カードからopenしURLを同期、task編集・comment CRUD・board再取得・closeまで連携する", async () => {
		const api = createApiMock();
		const { router } = renderBoard(ROUTES.PROJECT("project-1"), api.fetchMock);

		fireEvent.click(await screen.findByRole("listitem", { name: /結合テスト対象/ }));
		await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.TASK("project-1", "task-1")));
		const dialog = await screen.findByRole("dialog", { name: "タスク詳細" });
		await screen.findByRole("textbox", { name: "タイトル" });
		expect(await screen.findByText("既存コメント")).toBeInTheDocument();
		expect(screen.getByLabelText("期限")).toHaveValue("2026-09-09T23:59");
		await waitFor(() => expect(screen.getByRole("option", { name: "佐藤 花子（無効）" })).toBeDisabled());
		fireEvent.change(screen.getByLabelText("担当者"), { target: { value: "user-3" } });
		await waitFor(() => expect(screen.getByLabelText("担当者")).toHaveValue("user-3"));
		fireEvent.change(screen.getByLabelText("期限"), { target: { value: "2026-09-10T00:00" } });
		await waitFor(() => {
			const request = api.fetchMock.mock.calls.find(([url, init]) => {
				if (!String(url).endsWith("/tasks/task-1") || init?.method !== "PATCH") return false;
				return JSON.parse(String(init.body)).due_at !== undefined;
			});
			expect(JSON.parse(String(request?.[1]?.body)).due_at).toBe("2026-09-09T15:00:00.000Z");
		});

		const title = screen.getByLabelText("タイトル");
		fireEvent.change(title, { target: { value: "編集後タイトル" } });
		fireEvent.blur(title);
		expect(await screen.findByDisplayValue("編集後タイトル")).toBeInTheDocument();

		fireEvent.change(screen.getByRole("textbox", { name: "コメント" }), { target: { value: "投稿コメント" } });
		fireEvent.click(screen.getByRole("button", { name: "投稿" }));
		expect(await screen.findByText("投稿コメント")).toBeInTheDocument();
		expect(await screen.findByText("コメント: 2件")).toBeInTheDocument();
		expect(screen.getByRole("textbox", { name: "コメント" })).toHaveValue("");

		fireEvent.click(screen.getAllByRole("button", { name: "編集" })[0]);
		const commentEditor = screen.getByLabelText("コメントを編集");
		fireEvent.change(commentEditor, { target: { value: "編集済みコメント" } });
		fireEvent.click(screen.getByRole("button", { name: "保存" }));
		await waitFor(() => expect(api.fetchMock.mock.calls.some(([url, init]) => String(url).includes("/comments/") && init?.method === "PATCH")).toBe(true));
		expect(await screen.findByText("編集済みコメント")).toBeInTheDocument();

		vi.spyOn(window, "confirm").mockReturnValue(true);
		const firstComment = within(screen.getByRole("region", { name: "コメント" })).getAllByRole("article")[0];
		fireEvent.click(within(firstComment).getByRole("button", { name: "削除" }));
		await waitFor(() => expect(api.fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/comments/comment-1") && init?.method === "DELETE")).toBe(true));
		expect(screen.queryByText("既存コメント")).not.toBeInTheDocument();
		expect(await screen.findByText("コメント: 1件")).toBeInTheDocument();

		fireEvent.keyDown(dialog, { key: "Escape" });
		await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.PROJECT("project-1")));
		expect(screen.queryByRole("dialog", { name: "タスク詳細" })).not.toBeInTheDocument();
		expect(api.fetchMock.mock.calls.filter(([url, init]) => String(url).includes("/projects/project-1/tasks") && (init?.method ?? "GET") === "GET")).toHaveLength(6);
	});

	it("直接URLで開き、ブラウザ戻るでboardへ戻る。タスク削除成功時もcloseしてboardを同期する", async () => {
		const api = createApiMock();
		const { router } = renderBoard(ROUTES.TASK("project-1", "task-1"), api.fetchMock, [
			ROUTES.PROJECT("project-1"),
			ROUTES.TASK("project-1", "task-1"),
		]);
		await screen.findByRole("dialog", { name: "タスク詳細" });
		await screen.findByRole("textbox", { name: "タイトル" });

		await act(async () => { await router.navigate(-1); });
		await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.PROJECT("project-1")));
		expect(screen.queryByRole("dialog", { name: "タスク詳細" })).not.toBeInTheDocument();

		taskDetailStore.reset();
		await act(async () => { await router.navigate(ROUTES.TASK("project-1", "task-1")); });
		await screen.findByRole("dialog", { name: "タスク詳細" });
		await screen.findByRole("textbox", { name: "タイトル" });
		vi.spyOn(window, "confirm").mockReturnValue(true);
		fireEvent.click(screen.getByRole("button", { name: "タスクを削除" }));
		await waitFor(() => expect(router.state.location.pathname).toBe(ROUTES.PROJECT("project-1")));
		expect(await screen.findAllByText("この列にはタスクがありません")).not.toHaveLength(0);
	});

	it("409 TASK_CONFLICT時は最新taskを再取得して競合表示し、再取得した値を表示する", async () => {
		const api = createApiMock();
		api.setConflict();
		renderBoard(ROUTES.TASK("project-1", "task-1"), api.fetchMock);
		await screen.findByRole("dialog", { name: "タスク詳細" });
		await screen.findByRole("textbox", { name: "タイトル" });

		const title = screen.getByLabelText("タイトル");
		fireEvent.change(title, { target: { value: "自分の編集" } });
		fireEvent.blur(title);

		expect(await screen.findByRole("alert")).toHaveTextContent("他のユーザーが更新したため最新の内容を再取得しました");
		expect(screen.getByDisplayValue("他ユーザーの最新タイトル")).toBeInTheDocument();
	});

	it("task/commentsの404ではURLを維持してnot foundを表示し、自動closeしない", async () => {
		const taskApi = createApiMock({ taskStatus: 404 });
		const missingView = renderBoard(ROUTES.TASK("project-1", "missing"), taskApi.fetchMock);
		const { router } = missingView;
		expect(await screen.findByText("タスクが見つかりません")).toBeInTheDocument();
		expect(router.state.location.pathname).toBe(ROUTES.TASK("project-1", "missing"));

		missingView.unmount();
		taskDetailStore.reset();
		const commentsApi = createApiMock({ commentsStatus: 404 });
		renderBoard(ROUTES.TASK("project-1", "task-1"), commentsApi.fetchMock);
		expect(await screen.findByText("コメントが見つかりません")).toBeInTheDocument();
	});

	it("API障害時はモーダルを維持して共通エラーを表示し、入力validationも画面内で止める", async () => {
		const api = createApiMock();
		const { router } = renderBoard(ROUTES.TASK("project-1", "task-1"), api.fetchMock);
		await screen.findByRole("dialog", { name: "タスク詳細" });
		await screen.findByRole("textbox", { name: "タイトル" });

		const title = screen.getByLabelText("タイトル");
		fireEvent.change(title, { target: { value: "" } });
		fireEvent.blur(title);
		expect(screen.getByText("タイトルは1〜150文字で入力してください")).toBeInTheDocument();

		fireEvent.change(screen.getByRole("textbox", { name: "コメント" }), { target: { value: "  " } });
		expect(screen.getByRole("button", { name: "投稿" })).toBeDisabled();

		api.setTaskFailure();
		fireEvent.change(title, { target: { value: "通信障害を検証" } });
		fireEvent.blur(title);
		expect(await screen.findByText("エラーが発生しました。しばらくしてから再度お試しください")).toBeInTheDocument();
		expect(router.state.location.pathname).toBe(ROUTES.TASK("project-1", "task-1"));
	});
});
