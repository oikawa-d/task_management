import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteAdminProject, listAdminProjects } from "../api/adminApi";
import type { ProjectFilters } from "../api/adminApi";

export function useAdminProjects(filters: ProjectFilters, enabled = true) { return useQuery({ queryKey: ["admin", "projects", filters], queryFn: () => listAdminProjects(filters), placeholderData: keepPreviousData, enabled }); }
export function useDeleteAdminProject() { const queryClient = useQueryClient(); return useMutation({ mutationFn: (projectId: string) => deleteAdminProject(projectId), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "projects"] }) }); }
