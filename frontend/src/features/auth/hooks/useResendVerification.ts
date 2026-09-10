import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { resendVerification } from "../api/authApi";
import type { AuthApiError } from "../api/authApi";

/** docs/detailed_design/screen/05_verify_email.md §4 No.2（202固定・存在有無を問わない） */
export function useResendVerification(): UseMutationResult<void, AuthApiError, { email: string }> {
	return useMutation({
		mutationKey: ["auth", "resendVerification"],
		mutationFn: ({ email }: { email: string }) => resendVerification(email),
	});
}
