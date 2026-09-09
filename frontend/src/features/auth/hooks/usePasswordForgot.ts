import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { requestPasswordReset } from "../api/authApi";
import type { AuthApiError } from "../api/authApi";

/**
 * docs/detailed_design/screen/03_password_forgot.md §9.1
 * 202固定のため成功時は常に同一処理（formState="sent"への遷移は呼び出し元が行う）。
 */
export function usePasswordForgot(): UseMutationResult<void, AuthApiError, { email: string }> {
	return useMutation({
		mutationKey: ["auth", "passwordForgot"],
		mutationFn: ({ email }: { email: string }) => requestPasswordReset(email),
	});
}
