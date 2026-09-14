import { create } from "zustand";

import type { ProjectSummary } from "../features/dashboard/api/types";

export interface ProjectState {
	/** ダッシュボードで選択中のプロジェクトID。未選択はnull。 */
	selectedProjectId: string | null;
	/** 直近に作成したプロジェクト。作成直後の選択反映とカレンダー連携で参照する。 */
	selectedProject: ProjectSummary | null;
	selectProject: (project: ProjectSummary) => void;
	selectProjectById: (projectId: string) => void;
	clearSelectedProject: () => void;
}

const INITIAL_SELECTION = { selectedProjectId: null, selectedProject: null } as const;

/**
 * docs/detailed_design/screen/06_dashboard.md §5
 * プロジェクト一覧・作成の選択stateを保持する。一覧そのものはTanStack Queryが
 * 保持するため、本storeはサーバーデータを複製せず選択の事実のみを持つ。
 */
export const useProjectStore = create<ProjectState>()((set) => ({
	...INITIAL_SELECTION,
	selectProject: (project) => set({ selectedProjectId: project.id, selectedProject: project }),
	selectProjectById: (projectId) =>
		set((state) => ({
			selectedProjectId: projectId,
			selectedProject: state.selectedProject?.id === projectId ? state.selectedProject : null,
		})),
	clearSelectedProject: () => set({ ...INITIAL_SELECTION }),
}));
