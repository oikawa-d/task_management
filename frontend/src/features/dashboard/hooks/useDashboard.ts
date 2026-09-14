import { useMemo } from "react";

import type { CalendarTaskParams, ProjectListParams, ProjectSummary } from "../api/types";
import { useProjectStore } from "../../../stores/projectStore";
import { useCalendarTasks } from "./useCalendarTasks";
import { useCreateProject } from "./useCreateProject";
import { useProjects } from "./useProjects";

export interface UseDashboardOptions {
	projectsParams?: ProjectListParams;
	calendarParams?: CalendarTaskParams;
}

export interface DashboardState {
	projectsQuery: ReturnType<typeof useProjects>;
	createProjectMutation: ReturnType<typeof useCreateProject>;
	calendarQuery: ReturnType<typeof useCalendarTasks>;
	selectedProjectId: string | null;
	selectedProject: ProjectSummary | null;
	selectProject: (projectId: string) => void;
	clearSelectedProject: () => void;
}

export function useDashboard(options: UseDashboardOptions = {}): DashboardState {
	const projectsQuery = useProjects(options.projectsParams);
	const createProjectMutation = useCreateProject();
	const calendarQuery = useCalendarTasks(options.calendarParams);
	const selectedProjectId = useProjectStore((state) => state.selectedProjectId);
	const selectProject = useProjectStore((state) => state.selectProject);
	const clearSelectedProject = useProjectStore((state) => state.clearSelectedProject);
	const selectedProject = useMemo<ProjectSummary | null>(
		() => projectsQuery.data?.items.find((project) => project.id === selectedProjectId) ?? null,
		[projectsQuery.data?.items, selectedProjectId],
	);

	return {
		projectsQuery,
		createProjectMutation,
		calendarQuery,
		selectedProjectId,
		selectedProject,
		selectProject,
		clearSelectedProject,
	};
}
