import { beforeEach, describe, expect, it } from "vitest";

import type { ProjectSummary } from "../features/dashboard/api/types";
import { useProjectStore } from "./projectStore";

function buildProject(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
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

describe("projectStore", () => {
	beforeEach(() => {
		useProjectStore.getState().clearSelectedProject();
	});

	it("初期状態は未選択である", () => {
		expect(useProjectStore.getState().selectedProjectId).toBeNull();
		expect(useProjectStore.getState().selectedProject).toBeNull();
	});

	it("selectProjectでIDとプロジェクト本体を保持する", () => {
		const project = buildProject();
		useProjectStore.getState().selectProject(project);

		expect(useProjectStore.getState().selectedProjectId).toBe("project-1");
		expect(useProjectStore.getState().selectedProject).toEqual(project);
	});

	it("selectProjectByIdは同一IDのときだけ保持済みプロジェクトを維持する", () => {
		const project = buildProject();
		useProjectStore.getState().selectProject(project);

		useProjectStore.getState().selectProjectById("project-1");
		expect(useProjectStore.getState().selectedProject).toEqual(project);

		useProjectStore.getState().selectProjectById("project-2");
		expect(useProjectStore.getState().selectedProjectId).toBe("project-2");
		expect(useProjectStore.getState().selectedProject).toBeNull();
	});

	it("clearSelectedProjectで未選択へ戻す", () => {
		useProjectStore.getState().selectProject(buildProject());
		useProjectStore.getState().clearSelectedProject();

		expect(useProjectStore.getState().selectedProjectId).toBeNull();
		expect(useProjectStore.getState().selectedProject).toBeNull();
	});
});
