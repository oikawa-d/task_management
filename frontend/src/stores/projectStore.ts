import { create } from "zustand";

export interface ProjectState {
	/** ダッシュボードで選択中のプロジェクトID。未選択はnull。 */
	selectedProjectId: string | null;
	selectProject: (projectId: string) => void;
	clearSelectedProject: () => void;
}

const INITIAL_SELECTION = { selectedProjectId: null } as const;

/**
 * docs/detailed_design/screen/06_dashboard.md §5
 * プロジェクト一覧・作成の選択stateを保持する。一覧そのものはTanStack Queryが
 * 保持するため、本storeはプロジェクト本体を保持せず選択IDのみを持つ。
 */
export const useProjectStore = create<ProjectState>()((set) => ({
	...INITIAL_SELECTION,
	selectProject: (selectedProjectId) => set({ selectedProjectId }),
	clearSelectedProject: () => set(INITIAL_SELECTION),
}));
