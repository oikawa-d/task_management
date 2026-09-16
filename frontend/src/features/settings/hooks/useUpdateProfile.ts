import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { ApiError } from "../../../api/errors";
import { useAuthStore } from "../../../auth/authStore";
import { updateMyProfile } from "../api/profileApi";
import type { ProfilePatchInput, UserProfile } from "../types";
import { USER_PROFILE_QUERY_KEY } from "./useUserProfile";

export function useUpdateProfile(): UseMutationResult<UserProfile, ApiError, ProfilePatchInput> {
	const queryClient = useQueryClient();
	return useMutation({
		mutationKey: ["users", "me", "update"],
		mutationFn: (payload) => updateMyProfile(payload),
		onSuccess: async (profile) => {
			useAuthStore.getState().updateUser({
				display_name: profile.last_name && profile.first_name
					? `${profile.last_name} ${profile.first_name}`
					: profile.username,
			});
			await queryClient.invalidateQueries({ queryKey: USER_PROFILE_QUERY_KEY });
		},
	});
}
