import { Outlet } from "react-router-dom";

import styles from "./AuthLayout.module.css";

/**
 * 未認証画面（ログイン・会員登録・パスワード再設定・メール認証）共通のレイアウト。
 * 基本設計 05_frontend.md §2「画面一覧とルーティング」の AuthLayout に対応する。
 */
export function AuthLayout() {
	return (
		<div className={styles.container}>
			<div className={styles.card}>
				<Outlet />
			</div>
		</div>
	);
}
