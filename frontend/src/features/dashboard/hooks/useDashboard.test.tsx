import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as projectsApi from "../api/projectsApi";
import type { ProjectSummary } from "../api/types";
import { useProjectStore } from "../../../stores/projectStore";
import { useDashboard } from "./useDashboard";

function project(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
	return {
		id: "project-1",
		name: "Cerberus開発",
		description: null,
		owner: { id: "user-1", username: "taro", display_name: "山田 太郎" },
		member_count: 1,
		task_counts: { todo: 0, in_progress: 0, done: 0 },
		is_owner: true,
		is_active: true,
		start_at: null,
		end_at: null,
		created_at: "2026-09-01T00:00:00Z",
		...overrides,
	};
}

function wrapper({ children }: { children: ReactNode }) {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useDashboard", () => {
	afterEach(() => {
		useProjectStore.getState().clearSelectedProject();
		vi.restoreAllMocks();
	});

	it("一覧・カレンダー取得と作成mutation、選択IDをまとめて公開する", async () => {
		const created = project({ id: "project-2", name: "新プロジェクト" });
		const getProjects = vi.spyOn(projectsApi, "getProjects").mockResolvedValue({
			items: [project()],
			meta: { page: 1, per_page: 20, total: 1, total_pages: 1 },
		});
		const getCalendarTasks = vi.spyOn(projectsApi, "getCalendarTasks").mockResolvedValue([]);
		const createProject = vi.spyOn(projectsApi, "createProject").mockResolvedValue(created);
		const calendarParams = { from: "2026-09-01", to: "2026-10-12", scope: "me" as const };
		const { result } = renderHook(() => useDashboard({ calendarParams }), { wrapper });

		await waitFor(() => expect(result.current.projectsQuery.data?.items).toEqual([project()]));
		await waitFor(() => expect(getCalendarTasks).toHaveBeenCalledWith(calendarParams));
		expect(getProjects).toHaveBeenCalledWith({});

		act(() => result.current.selectProject("project-1"));
		expect(result.current.selectedProjectId).toBe("project-1");
		expect(result.current.selectedProject).toEqual(project());
		await act(async () => {
			await result.current.createProjectMutation.mutateAsync({ name: "新プロジェクト", description: null });
		});

		expect(createProject).toHaveBeenCalledWith({ name: "新プロジェクト", description: null });
		expect(result.current.selectedProjectId).toBe("project-2");
	});
});
