import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { ApiError } from "../../../api/errors";
import { changeMyPassword } from "../api/profileApi";
import type { PasswordChangeInput } from "../types";

export function useChangePassword(): UseMutationResult<void, ApiError, PasswordChangeInput> {
	return useMutation({
		mutationKey: ["users", "me", "password"],
		mutationFn: (payload) => changeMyPassword(payload),
	});
}
