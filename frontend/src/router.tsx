import { Navigate, createBrowserRouter } from "react-router-dom";

import { RequireAdmin } from "./auth/guards";
import { AdminUsersPage } from "./features/admin/pages/AdminUsersPage";
import { LoginPage } from "./features/auth/pages/LoginPage";
import { DashboardPage } from "./features/dashboard/pages/DashboardPage";
import { AppLayout } from "./layouts/AppLayout";
import { ROUTES } from "./routes";

export const router = createBrowserRouter([
	{
		path: ROUTES.ROOT,
		element: <Navigate to={ROUTES.LOGIN} replace />,
	},
	{
		path: ROUTES.LOGIN,
		element: <LoginPage />,
	},
	{
		element: <AppLayout />,
		children: [
			{
				path: ROUTES.DASHBOARD,
				element: <DashboardPage />,
			},
			{
				element: <RequireAdmin />,
				children: [
					{
						path: ROUTES.ADMIN_USERS,
						element: <AdminUsersPage />,
					},
				],
			},
		],
	},
]);
