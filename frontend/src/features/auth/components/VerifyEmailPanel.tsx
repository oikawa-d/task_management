import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { useResendVerification } from "../hooks/useResendVerification";
import type { ResendVerificationFormValues } from "../types";
import { createZodResolver, resendVerificationSchema } from "../validation";

export type VerifyEmailPhase = "noToken" | "verifying" | "success" | "error";

export interface VerifyEmailPanelProps {
	phase: VerifyEmailPhase;
	errorMessage?: string;
	/** phase==="success"時、即時遷移リンククリックで呼ばれる（自動遷移タイマーは呼び出し元が管理） */
	onRedirectNow?: () => void;
}

/**
 * メール認証結果表示コンポーネント（検証中/成功/失敗の表示 + 認証メール再送フォーム）。
 * docs/detailed_design/screen/05_verify_email.md
 */
export function VerifyEmailPanel({ phase, errorMessage, onRedirectNow }: VerifyEmailPanelProps) {
	const resendEmailRef = useRef<HTMLInputElement>(null);

	useEffect(() => {
		if (phase === "error" || phase === "noToken") {
			resendEmailRef.current?.focus();
		}
	}, [phase]);

	return (
		<div>
			{phase === "verifying" && (
				<p role="status">メールアドレスを確認中です</p>
			)}
			{phase === "success" && (
				<div role="status" aria-live="polite">
					<p>メール認証が完了しました</p>
					<p>3秒後にログイン画面へ移動します</p>
					<button type="button" onClick={() => onRedirectNow?.()}>
						今すぐ移動する
					</button>
				</div>
			)}
			{phase === "error" && (
				<p role="alert">{errorMessage ?? "リンクの有効期限が切れているか、既に使用済みです"}</p>
			)}
			{phase === "noToken" && <p>リンクが不正です</p>}
			{(phase === "error" || phase === "noToken") && (
				<ResendVerificationForm inputRef={resendEmailRef} />
			)}
		</div>
	);
}

interface ResendVerificationFormProps {
	inputRef: React.RefObject<HTMLInputElement | null>;
}

function ResendVerificationForm({ inputRef }: ResendVerificationFormProps) {
	const [sent, setSent] = useState(false);
	const mutation = useResendVerification();
	const {
		register,
		handleSubmit,
		watch,
		formState: { errors },
	} = useForm<ResendVerificationFormValues>({
		defaultValues: { email: "" },
		resolver: createZodResolver(resendVerificationSchema),
		mode: "onChange",
	});
	const email = watch("email");
	const { ref: emailRegisterRef, ...emailRegistration } = register("email");

	const submit = async (values: ResendVerificationFormValues) => {
		// 存在有無・認証済み有無・再送間隔内かに関わらず常に同一応答（202）のため、
		// APIエラー（ネットワークエラー等）以外は常に送信済み表示にする。
		try {
			await mutation.mutateAsync(values);
		} finally {
			setSent(true);
		}
	};

	return (
		<form onSubmit={handleSubmit(submit)} noValidate>
			<label htmlFor="verify-email-resend-email">メールアドレス</label>
			<input
				id="verify-email-resend-email"
				type="email"
				aria-invalid={Boolean(errors.email)}
				aria-describedby={errors.email ? "verify-email-resend-email-error" : undefined}
				{...emailRegistration}
				ref={(element) => {
					emailRegisterRef(element);
					inputRef.current = element;
				}}
			/>
			{errors.email && (
				<span id="verify-email-resend-email-error" role="alert">
					{errors.email.message}
				</span>
			)}
			<button type="submit" disabled={mutation.isPending || Boolean(errors.email) || !email}>
				{mutation.isPending ? "送信中…" : "認証メールを再送する"}
			</button>
			{sent && <p role="status">送信しました。しばらくしても届かない場合は迷惑メールフォルダをご確認ください</p>}
		</form>
	);
}
