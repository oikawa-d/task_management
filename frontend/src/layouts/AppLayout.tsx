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
			<nav aria-label="サイドバー">
				<Link to={ROUTES.DASHBOARD}>home</Link>
				{isAdmin ? <Link to={ROUTES.ADMIN_USERS}>管理</Link> : null}
			</nav>
			<main>
				<Outlet />
			</main>
		</div>
	);
}
