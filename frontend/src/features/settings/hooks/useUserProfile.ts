import { useQuery } from "@tanstack/react-query";

import { getMyProfile } from "../api/profileApi";

export const USER_PROFILE_QUERY_KEY = ["users", "me"] as const;

export function useUserProfile() {
	return useQuery({
		queryKey: USER_PROFILE_QUERY_KEY,
		queryFn: () => getMyProfile(),
	});
}
