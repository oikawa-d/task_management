import type { QueryClient } from "@tanstack/react-query";

import { queryClient as appQueryClient } from "../lib/queryClient";
import { useProjectStore } from "../stores/projectStore";
import { taskDetailStore } from "../stores/taskDetailStore";

/** ユーザー切替時に、前ユーザーのクライアント側データを破棄する。 */
export function clearUserSessionState(client: QueryClient = appQueryClient): void {
	useProjectStore.getState().clearSelectedProject();
	taskDetailStore.reset();
	client.clear();
}
