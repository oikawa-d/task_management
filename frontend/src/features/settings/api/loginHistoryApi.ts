import { getApiClient } from "../../../api/client";

export interface LoginHistoryItem {
	id: string;
	login_method: "session" | "jwt" | "oauth_google";
	ip_address: string | null;
	user_agent: string | null;
	success: boolean;
	failure_reason: string | null;
	created_at: string;
}

export interface LoginHistoryResponse {
	items: LoginHistoryItem[];
	meta: { limit: number; count: number };
}

export async function getLoginHistory(): Promise<LoginHistoryResponse> {
	const { data } = await getApiClient().get<LoginHistoryResponse>("/users/me/login-history");
	return data;
}
