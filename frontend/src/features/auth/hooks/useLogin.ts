import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { resolveAuthAdapter } from "../../../api/authAdapter/client";
import { useAuthStore } from "../../../auth/authStore";
import { fetchAuthMe } from "../api/oauthCallbackApi";
import { login } from "../api/authApi";
import type { AuthApiError } from "../api/authApi";
import type { LoginFormValues, LoginResponse } from "../types";

/**
 * design doc: docs/detailed_design/screen/01_login.md §9.1 useLogin
 *
 * 1. `endpoints/auth.ts#login`（`api/authApi.ts#login`）を呼ぶ
 * 2. 成功時に既存の `AuthAdapter#onLoginSuccess` へ結果を渡し、`GET /auth/me` で最新状態を取得して
 *    `authStore` を `authenticated` に更新する（`frontend/src/auth/`・`frontend/src/api/authAdapter/` を経由）
 * 3. 失敗時は `AuthApiError` をそのまま呼び出し元（LoginForm）へ伝播する
 */
export function useLogin(): UseMutationResult<LoginResponse | undefined, AuthApiError, LoginFormValues> {
	return useMutation({
		mutationKey: ["auth", "login"],
		mutationFn: async (values: LoginFormValues) => {
			const response = await login(values);
			const adapter = await resolveAuthAdapter();
			adapter.onLoginSuccess(response ?? {});
			const me = await fetchAuthMe();
			useAuthStore.getState().setAuthenticated({ id: me.id, role: me.role });
			return response;
		},
	});
}
