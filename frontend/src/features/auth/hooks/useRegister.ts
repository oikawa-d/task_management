import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { register } from "../api/authApi";
import type { AuthApiError } from "../api/authApi";
import type { RegisterResponse, RegisterSubmitPayload } from "../types";

/**
 * design doc: docs/detailed_design/screen/02_register.md §9.2 useRegister
 *
 * `endpoints/auth.ts#register`（`api/authApi.ts#register`）を呼ぶのみ。
 * 登録は自動ログインしないため `authStore` は更新しない（呼び出し元の `RegisterForm` が
 * 成功時に `onSuccess(email)` を呼び、`RegisterPage` が `/login` へ遷移する）。
 */
export function useRegister(): UseMutationResult<RegisterResponse, AuthApiError, RegisterSubmitPayload> {
	return useMutation({
		mutationKey: ["auth", "register"],
		mutationFn: (payload: RegisterSubmitPayload) => register(payload),
	});
}
