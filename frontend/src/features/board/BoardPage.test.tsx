import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { BoardPage, type BoardPageProps } from "./BoardPage";
import type { BoardResponse } from "./types";

const board: BoardResponse = {
	columns: {
		todo: [{ id: "task-todo", title: "未着手タスク" }],
		in_progress: [{ id: "task-progress", title: "進行中タスク" }],
		done: [{ id: "task-done", title: "完了タスク" }],
	},
};

function renderBoard(path = "/projects/project-1", props: BoardPageProps = { board }) {
	const router = createMemoryRouter(
		[
			{ path: "/projects/:projectId", element: <BoardPage {...props} /> },
			{ path: "/projects/:projectId/tasks/:taskId", element: <BoardPage {...props} /> },
		],
		{ initialEntries: [path] },
	);
	render(<RouterProvider router={router} />);
	return router;
}

describe("BoardPage", () => {
	it("renders the project id and all status columns with task counts", () => {
		renderBoard();

		expect(screen.getByRole("heading", { name: "プロジェクト project-1" })).toBeInTheDocument();
		expect(screen.getByRole("region", { name: "未着手" })).toHaveTextContent("未着手 (1)");
		expect(screen.getByRole("region", { name: "進行中" })).toHaveTextContent("進行中 (1)");
		expect(screen.getByRole("region", { name: "完了" })).toHaveTextContent("完了 (1)");
	});

	it("shows the not-found state without rendering board content", () => {
		renderBoard("/projects/missing", { board: null, errorStatus: 404 });

		expect(screen.getByRole("alert")).toHaveTextContent("プロジェクトが見つかりません");
		expect(screen.queryByRole("region", { name: "未着手" })).not.toBeInTheDocument();
	});

	it("shows a loading state while the board is unavailable", () => {
		renderBoard("/projects/project-1", { board: null, isLoading: true });

		expect(screen.getByRole("status")).toHaveTextContent("ボードを読み込み中");
	});
});
