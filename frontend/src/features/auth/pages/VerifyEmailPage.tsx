import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ROUTES } from "../../../routes";
import { AuthApiError, verifyEmail } from "../api/authApi";
import { VerifyEmailPanel, type VerifyEmailPhase } from "../components/VerifyEmailPanel";
import { EMAIL_VERIFY_REDIRECT_DELAY_MS } from "../config/pageConfig";
import { useHashToken } from "../hooks/useHashToken";

/**
 * メール認証画面（/verify-email#token=...）。
 * fragmentから抽出したtokenを一度だけ検証し、結果表示とログイン画面への遷移を管理する。
 */
export function VerifyEmailPage() {
	const navigate = useNavigate();
	const { token, ready } = useHashToken();
	const [phase, setPhase] = useState<VerifyEmailPhase>("verifying");
	const [errorMessage, setErrorMessage] = useState<string | undefined>();
	const verifyRequestedRef = useRef(false);

	useEffect(() => {
		if (!ready || verifyRequestedRef.current) {
			return;
		}
		verifyRequestedRef.current = true;

		if (!token) {
			setPhase("noToken");
			return;
		}

		let mounted = true;
		setPhase("verifying");
		void verifyEmail(token)
			.then(() => {
				if (mounted) setPhase("success");
			})
			.catch((error: unknown) => {
				if (!mounted) return;
				if (error instanceof AuthApiError && error.status === 400 && error.code === "INVALID_VERIFY_TOKEN") {
					setErrorMessage(undefined);
				} else {
					setErrorMessage("エラーが発生しました。しばらくしてから再度お試しください");
				}
				setPhase("error");
			});

		return () => {
			mounted = false;
		};
	}, [ready, token]);

	useEffect(() => {
		if (phase !== "success") {
			return;
		}
		const timer = window.setTimeout(() => {
			navigate(ROUTES.LOGIN, { state: { emailVerified: true } });
		}, EMAIL_VERIFY_REDIRECT_DELAY_MS);
		return () => window.clearTimeout(timer);
	}, [navigate, phase]);

	const redirectNow = () => navigate(ROUTES.LOGIN, { state: { emailVerified: true } });

	return (
		<section aria-labelledby="verify-email-heading">
			<h1 id="verify-email-heading">メールアドレスを確認中です</h1>
			{ready ? (
				<VerifyEmailPanel phase={phase} errorMessage={errorMessage} onRedirectNow={redirectNow} />
			) : (
				<p role="status">確認しています…</p>
			)}
		</section>
	);
}
