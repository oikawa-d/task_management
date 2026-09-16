import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ROUTES } from "../../../routes";
import { useHashToken } from "../hooks/useHashToken";

export type PasswordResetFormSlotProps = {
	token: string;
};

export interface PasswordResetPageProps {
	form?: (props: PasswordResetFormSlotProps) => ReactNode;
	invalidLinkMessage?: ReactNode;
}

function DefaultPasswordResetForm({ token }: PasswordResetFormSlotProps) {
	return (
		<form aria-label="パスワード再設定フォーム" data-token={token}>
			<p>パスワード再設定フォームを表示します。</p>
		</form>
	);
}

const DEFAULT_INVALID_LINK_MESSAGE = "リンクの有効期限が切れているか、既に使用済みです";

/**
 * パスワード再設定画面（/password/reset#token=...）。
 * 入力フォーム本体（PasswordResetForm）は別issue（#152）の担当のため、
 * 本ページはfragmentからのtoken抽出・除去とフォームスロットへの受け渡し、
 * token不正時の再要求導線のみを担う。
 */
export function PasswordResetPage({
	form = DefaultPasswordResetForm,
	invalidLinkMessage = <>{DEFAULT_INVALID_LINK_MESSAGE}</>,
}: PasswordResetPageProps) {
	const { token, ready } = useHashToken();

	return (
		<section aria-labelledby="password-reset-heading">
			<h1 id="password-reset-heading">新しいパスワードを設定</h1>
			{!ready ? null : token ? (
				form({ token })
			) : (
				<div>
					<p role="alert">{invalidLinkMessage}</p>
					<Link to={ROUTES.PASSWORD_FORGOT}>もう一度リセットを申請する</Link>
				</div>
			)}
		</section>
	);
}
