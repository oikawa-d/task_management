import { useQuery } from "@tanstack/react-query";

import { getLoginHistory } from "../api/loginHistoryApi";

export function useLoginHistory(enabled: boolean) {
	return useQuery({
		queryKey: ["users", "me", "login-history"],
		queryFn: getLoginHistory,
		enabled,
	});
}
