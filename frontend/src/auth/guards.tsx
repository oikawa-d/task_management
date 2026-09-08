import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "./authStore";
import { ROUTES } from "../routes";

export function RequireAdmin() {
	const status = useAuthStore((state) => state.status);
	const user = useAuthStore((state) => state.user);

	if (status !== "authenticated") {
		return <Navigate to={ROUTES.LOGIN} replace />;
	}

	if (user?.role !== "admin") {
		return <Navigate to={ROUTES.DASHBOARD} replace />;
	}

	return <Outlet />;
}
