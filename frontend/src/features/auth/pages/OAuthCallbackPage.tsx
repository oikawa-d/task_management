import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { resolveAuthAdapter } from "../../../api/authAdapter/client";
import { useAuthStore } from "../../../auth/authStore";
import { ROUTES } from "../../../routes";
import { OAuthCallbackApiError } from "../api/oauthCallbackApi";
import { useAuthMeQuery } from "../hooks/useAuthMeQuery";
import { useOAuthExchange } from "../hooks/useOAuthExchange";
import { isSafeRelativePath } from "../utils/url";

type CallbackState = "processing" | "failed";

const ERROR_MESSAGES = {
	oauthHandoffInvalid: "ログインセッションの有効期限が切れました。もう一度お試しください",
	userInactive: "アカウントが無効化されています。管理者にお問い合わせください",
	sessionConfirmFailed: "ログイン処理に失敗しました",
	invalidAccess: "不正なアクセスです",
	generic: "処理に失敗しました",
} as const;

function parseHash(hash: string): { code: string | null; redirectTo: string | null } {
	const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
	return {
		code: params.get("code"),
		redirectTo: params.get("redirect_to"),
	};
}

function clearHash(): void {
	window.history.replaceState(null, "", ROUTES.OAUTH_CALLBACK);
}

/**
 * design doc: docs/detailed_design/screen/11_oauth_callback.md
 * OAuthコールバック中継画面。AuthLayout/AppLayoutいずれにも属さず、AuthProviderの
 * 未認証リダイレクトより先に本画面自身の交換・確認処理が完了する前提の例外パス。
 */
export function OAuthCallbackPage() {
	const navigate = useNavigate();
	const exchangeMutation = useOAuthExchange();
	const { refetch: fetchMe } = useAuthMeQuery();
	const exchangeRanRef = useRef(false);
	const [callbackState, setCallbackState] = useState<CallbackState>("processing");
	const [errorMessage, setErrorMessage] = useState<string>(ERROR_MESSAGES.generic);
	const backToLoginRef = useRef<HTMLAnchorElement>(null);

	useEffect(() => {
		if (exchangeRanRef.current) {
			return;
		}
		exchangeRanRef.current = true;

		function fail(message: string): void {
			setErrorMessage(message);
			setCallbackState("failed");
		}

		async function runCallback(): Promise<void> {
			const { code, redirectTo: hashRedirectTo } = parseHash(window.location.hash);
			const adapter = await resolveAuthAdapter();

			let redirectTo = hashRedirectTo;

			if (adapter.mode === "jwt") {
				if (!code) {
					fail(ERROR_MESSAGES.invalidAccess);
					return;
				}

				try {
					const exchangeResult = await exchangeMutation.mutateAsync({ code });
					clearHash();
					redirectTo = exchangeResult.redirect_to;
				} catch (error) {
					clearHash();
					if (error instanceof OAuthCallbackApiError && error.code === "USER_INACTIVE") {
						fail(ERROR_MESSAGES.userInactive);
					} else if (error instanceof OAuthCallbackApiError && error.code === "OAUTH_HANDOFF_INVALID") {
						fail(ERROR_MESSAGES.oauthHandoffInvalid);
					} else {
						fail(ERROR_MESSAGES.generic);
					}
					return;
				}
			} else if (!isSafeRelativePath(redirectTo)) {
				redirectTo = ROUTES.DASHBOARD;
			}

			let me;
			try {
				me = await fetchMe();
			} catch {
				fail(ERROR_MESSAGES.sessionConfirmFailed);
				return;
			}

			if (adapter.mode === "session") {
				clearHash();
			}

			useAuthStore.getState().setAuthenticated({ id: me.id, role: me.role });

			if (!me.profile_completed) {
				navigate(`${ROUTES.SETTINGS}?complete_profile=1`, { replace: true });
				return;
			}
			navigate(redirectTo ?? ROUTES.DASHBOARD, { replace: true });
		}

		void runCallback();
		// マウント時に1度だけ実行する（exchangeRanRefにより多重実行自体も防止する）
	}, []);

	useEffect(() => {
		if (callbackState === "failed") {
			backToLoginRef.current?.focus();
		}
	}, [callbackState]);

	return (
		<section>
			{callbackState === "processing" && (
				<p role="status" aria-live="polite">
					ログイン処理中です…
				</p>
			)}
			{callbackState === "failed" && (
				<div role="alert">
					<p>{errorMessage}</p>
					<a
						ref={backToLoginRef}
						href={ROUTES.LOGIN}
						onClick={(event) => {
							event.preventDefault();
							navigate(ROUTES.LOGIN, { replace: true });
						}}
					>
						ログイン画面へ戻る
					</a>
				</div>
			)}
		</section>
	);
}
