import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { forceLogout, listAdminUsers, patchAdminUserRole, patchAdminUserStatus } from "../api/adminApi";
import type { AdminRole, UserFilters } from "../api/adminApi";

export function useAdminUsers(filters: UserFilters, enabled = true) { return useQuery({ queryKey: ["admin", "users", filters], queryFn: () => listAdminUsers(filters), placeholderData: keepPreviousData, enabled }); }
function useAdminMutation<T>(mutationFn: (input: T) => Promise<unknown>) { const queryClient = useQueryClient(); return useMutation({ mutationFn, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }) }); }
export function useChangeRole() { return useAdminMutation<{ userId: string; role: AdminRole }>(({ userId, role }) => patchAdminUserRole(userId, role)); }
export function useChangeStatus() { return useAdminMutation<{ userId: string; isActive: boolean }>(({ userId, isActive }) => patchAdminUserStatus(userId, isActive)); }
export function useForceLogout() { return useAdminMutation<string>((userId) => forceLogout(userId)); }
