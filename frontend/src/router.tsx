import { Navigate, createBrowserRouter } from "react-router-dom";

import { RequireAdmin, RequireAuth, RequireGuest } from "./auth/guards";
import { AdminUsersPage } from "./features/admin/pages/AdminUsersPage";
import { LoginPage } from "./features/auth/pages/LoginPage";
import { DashboardPage } from "./features/dashboard/pages/DashboardPage";
import { SettingsPage } from "./features/settings/pages/SettingsPage";
import { AppLayout } from "./layouts/AppLayout";
import { ROUTES } from "./routes";

export const appRoutes = [
	{
		path: ROUTES.ROOT,
		element: <Navigate to={ROUTES.LOGIN} replace />,
	},
	{
		element: <RequireGuest />,
		children: [{ path: ROUTES.LOGIN, element: <LoginPage /> }],
	},
	{
		element: <AppLayout />,
		children: [
			{
				element: <RequireAuth />,
				children: [
					{ path: ROUTES.DASHBOARD, element: <DashboardPage /> },
					{ path: ROUTES.SETTINGS, element: <SettingsPage /> },
				],
			},
			{
				element: <RequireAdmin />,
				children: [{ path: ROUTES.ADMIN_USERS, element: <AdminUsersPage /> }],
			},
		],
	},
];

export const router = createBrowserRouter(appRoutes);
