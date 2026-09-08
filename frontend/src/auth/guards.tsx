import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "./authStore";
import { ROUTES } from "../routes";

export function RequireAuth() {
	const status = useAuthStore((state) => state.status);

	if (status !== "authenticated") {
		return <Navigate to={ROUTES.LOGIN} replace />;
	}

	return <Outlet />;
}

export function RequireGuest() {
	const status = useAuthStore((state) => state.status);

	if (status === "authenticated") {
		return <Navigate to={ROUTES.DASHBOARD} replace />;
	}

	return <Outlet />;
}

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
