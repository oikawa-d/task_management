import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardPage } from "./BoardPage";

const task = {
	id: "task-1",
	title: "カンバンから開くタスク",
	description: null,
	status: "todo" as const,
	assignee: null,
	position: 0,
	version: 1,
	due_at: null,
	is_active: true,
	comment_count: 0,
	created_at: "2026-09-01T00:00:00Z",
	updated_at: "2026-09-01T00:00:00Z",
};

function jsonResponse(data: unknown) {
	return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}

describe("BoardPage and TaskDetailModal", () => {
	beforeEach(() => {
		vi.stubGlobal(
			"fetch",
			vi.fn(() => jsonResponse({
				project_id: "project-1",
				project_is_active: true,
				columns: { todo: [task], in_progress: [], done: [] },
			})),
		);
	});

	afterEach(() => vi.unstubAllGlobals());

	it("opens from a kanban card, synchronizes the URL, and closes back to the board", async () => {
		const router = createMemoryRouter(
			[
				{ path: "/projects/:projectId", element: <BoardPage /> },
				{ path: "/projects/:projectId/tasks/:taskId", element: <BoardPage /> },
			],
			{ initialEntries: ["/projects/project-1"] },
		);
		render(<RouterProvider router={router} />);

		fireEvent.click(await screen.findByRole("listitem", { name: /カンバンから開くタスク/ }));
		await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project-1/tasks/task-1"));
		expect(await screen.findByRole("dialog", { name: "タスク詳細" })).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
		await waitFor(() => expect(router.state.location.pathname).toBe("/projects/project-1"));
		expect(screen.queryByRole("dialog", { name: "タスク詳細" })).not.toBeInTheDocument();
	});
});
