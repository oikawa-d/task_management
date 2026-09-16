import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ROUTES } from "../../../routes";

export type PasswordForgotFormSlotProps = {
	onSent: () => void;
};

export interface PasswordForgotPageProps {
	form?: (props: PasswordForgotFormSlotProps) => ReactNode;
	sentMessage?: ReactNode;
}

function DefaultPasswordForgotForm({ onSent }: PasswordForgotFormSlotProps) {
	return (
		<form
			aria-label="パスワード再設定要求フォーム"
			onSubmit={(event) => {
				event.preventDefault();
				onSent();
			}}
		>
			<p>パスワード再設定要求フォームを表示します。</p>
		</form>
	);
}

const DEFAULT_SENT_MESSAGE =
	"ご登録のメールアドレス宛にパスワード再設定用のメールを送信しました。";

/**
 * パスワード再設定要求画面（/password/forgot）。
 * 送信フォーム本体（PasswordForgotForm）は別issue（#152）の担当のため、
 * 本ページはフォームを差し込み可能なスロットとして持ち、送信完了状態の
 * 管理とログイン画面への導線のみを担う。
 */
export function PasswordForgotPage({
	form = DefaultPasswordForgotForm,
	sentMessage = <>{DEFAULT_SENT_MESSAGE}</>,
}: PasswordForgotPageProps) {
	const [sent, setSent] = useState(false);
	const sentHeadingRef = useRef<HTMLHeadingElement>(null);

	useEffect(() => {
		if (sent) {
			sentHeadingRef.current?.focus();
		}
	}, [sent]);

	return (
		<section aria-labelledby="password-forgot-heading">
			<h1 id="password-forgot-heading">パスワードをお忘れの方</h1>
			{sent ? (
				<div>
					<h2 ref={sentHeadingRef} tabIndex={-1}>
						送信完了
					</h2>
					<p role="status" aria-live="polite">
						{sentMessage}
					</p>
				</div>
			) : (
				<>
					<p>登録済みのメールアドレスを入力してください</p>
					{form({ onSent: () => setSent(true) })}
				</>
			)}
			<Link to={ROUTES.LOGIN}>ログイン画面に戻る</Link>
		</section>
	);
}
