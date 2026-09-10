import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { resetPassword } from "../api/authApi";
import type { AuthApiError } from "../api/authApi";

export interface PasswordResetMutationInput {
	token: string;
	newPassword: string;
	passwordConfirm: string;
}

/** docs/detailed_design/screen/04_password_reset.md §9.2で利用するmutation */
export function usePasswordReset(): UseMutationResult<void, AuthApiError, PasswordResetMutationInput> {
	return useMutation({
		mutationKey: ["auth", "passwordReset"],
		mutationFn: ({ token, newPassword, passwordConfirm }: PasswordResetMutationInput) =>
			resetPassword({ token, new_password: newPassword, password_confirm: passwordConfirm }),
	});
}
