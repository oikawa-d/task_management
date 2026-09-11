import { useQuery } from "@tanstack/react-query";

import { getCalendarTasks } from "../api/projectsApi";
import type { CalendarTaskParams } from "../api/types";

export function useCalendarTasks(params: CalendarTaskParams, enabled = true) {
	return useQuery({
		queryKey: ["tasks-calendar", params.scope, params.project_id ?? null, params.from, params.to],
		queryFn: () => getCalendarTasks(params),
		enabled,
	});
}
