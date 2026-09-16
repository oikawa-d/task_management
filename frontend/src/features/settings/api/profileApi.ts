import type { AxiosInstance } from "axios";

import { getApiClient } from "../../../api/client";
import type { PasswordChangeInput, ProfilePatchInput, UserProfile } from "../types";

export async function getMyProfile(client: AxiosInstance = getApiClient()): Promise<UserProfile> {
	const { data } = await client.get<UserProfile>("/users/me");
	return data;
}

export async function updateMyProfile(
	payload: ProfilePatchInput,
	client: AxiosInstance = getApiClient(),
): Promise<UserProfile> {
	const { data } = await client.patch<UserProfile>("/users/me", payload);
	return data;
}

export async function changeMyPassword(
	payload: PasswordChangeInput,
	client: AxiosInstance = getApiClient(),
): Promise<void> {
	await client.put("/users/me/password", payload);
}
