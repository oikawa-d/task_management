import { requestJson } from "../../../api/http";
import type { PasswordChangeInput, ProfilePatchInput, UserProfile } from "../types";

export function getMyProfile(): Promise<UserProfile> {
	return requestJson("/users/me");
}

export async function updateMyProfile(
	payload: ProfilePatchInput,
): Promise<UserProfile> {
	return requestJson("/users/me", { method: "PATCH", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
}

export async function changeMyPassword(
	payload: PasswordChangeInput,
): Promise<void> {
	await requestJson("/users/me/password", { method: "PUT", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
}
