import { useQuery } from "@tanstack/react-query";

import { getCalendarTasks } from "../api/projectsApi";
import type { CalendarTaskParams } from "../api/types";

export function useCalendarTasks(params: CalendarTaskParams | undefined, enabled = params !== undefined) {
	return useQuery({
		queryKey: ["tasks-calendar", params?.scope ?? null, params?.project_id ?? null, params?.from ?? null, params?.to ?? null],
		queryFn: () => (params ? getCalendarTasks(params) : Promise.resolve([])),
		enabled,
	});
}
