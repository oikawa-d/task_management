import { Link, Outlet } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { ROUTES } from "../routes";

export function AppLayout() {
	const user = useAuthStore((state) => state.user);
	const isAdmin = user?.role === "admin";

	return (
		<div>
			<header>
				<span>Cerberus</span>
			</header>
			{/* 設定/ログアウト/通知ベルは #224 で追加予定の最小実装 */}
			<nav aria-label="サイドバー">
				<Link to={ROUTES.DASHBOARD}>home</Link>
				<Link to={ROUTES.SETTINGS}>設定</Link>
				{isAdmin ? <Link to={ROUTES.ADMIN_USERS}>管理</Link> : null}
			</nav>
			<main>
				<Outlet />
			</main>
		</div>
	);
}
