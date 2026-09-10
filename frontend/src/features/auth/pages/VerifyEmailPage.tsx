import type { ReactNode } from "react";

import { useHashToken } from "../hooks/useHashToken";

export type VerifyEmailResultSlotProps = {
	token: string | null;
};

export interface VerifyEmailPageProps {
	result?: (props: VerifyEmailResultSlotProps) => ReactNode;
}

function DefaultVerifyEmailResult({ token }: VerifyEmailResultSlotProps) {
	if (!token) {
		return (
			<div>
				<p role="alert">リンクが不正です</p>
				<form aria-label="認証メール再送フォーム">
					<p>認証メール再送フォームを表示します。</p>
				</form>
			</div>
		);
	}

	return (
		<div data-token={token}>
			<p role="status">メールアドレスを確認中です</p>
		</div>
	);
}

/**
 * メール認証画面（/verify-email#token=...）。
 * トークン検証・成功/失敗表示・再送フォーム（メール認証結果表示コンポーネント）は
 * 別issue（#152）の担当のため、本ページはfragmentからのtoken抽出・除去と
 * 結果表示スロットへの受け渡しのみを担う。
 */
export function VerifyEmailPage({ result = DefaultVerifyEmailResult }: VerifyEmailPageProps) {
	const { token, ready } = useHashToken();

	return (
		<section aria-labelledby="verify-email-heading">
			<h1 id="verify-email-heading">メールアドレスを確認中です</h1>
			{ready ? result({ token }) : null}
		</section>
	);
}
