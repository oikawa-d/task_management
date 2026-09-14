import { beforeEach, describe, expect, it } from "vitest";

import { useProjectStore } from "./projectStore";

describe("projectStore", () => {
	beforeEach(() => {
		useProjectStore.getState().clearSelectedProject();
	});

	it("初期状態は未選択である", () => {
		expect(useProjectStore.getState().selectedProjectId).toBeNull();
	});

	it("selectProjectで選択したIDだけを保持する", () => {
		useProjectStore.getState().selectProject("project-1");

		expect(useProjectStore.getState().selectedProjectId).toBe("project-1");
		expect("selectedProject" in useProjectStore.getState()).toBe(false);
	});

	it("clearSelectedProjectで未選択へ戻す", () => {
		useProjectStore.getState().selectProject("project-1");
		useProjectStore.getState().clearSelectedProject();

		expect(useProjectStore.getState().selectedProjectId).toBeNull();
	});
});
