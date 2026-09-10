import { Navigate, createBrowserRouter } from "react-router-dom";

import { RequireAdmin, RequireAuth, RequireGuest } from "./auth/guards";
import { AdminUsersPage } from "./features/admin/pages/AdminUsersPage";
import { LoginPage } from "./features/auth/pages/LoginPage";
import { OAuthCallbackPage } from "./features/auth/pages/OAuthCallbackPage";
import { PasswordForgotPage } from "./features/auth/pages/PasswordForgotPage";
import { PasswordResetPage } from "./features/auth/pages/PasswordResetPage";
import { RegisterPage } from "./features/auth/pages/RegisterPage";
import { VerifyEmailPage } from "./features/auth/pages/VerifyEmailPage";
import { DashboardPage } from "./features/dashboard/pages/DashboardPage";
import { BoardPage } from "./features/board/BoardPage";
import { SettingsPage } from "./features/settings/pages/SettingsPage";
import { AppLayout } from "./layouts/AppLayout";
import { AuthLayout } from "./layouts/AuthLayout";
import { ROUTES } from "./routes";

export const appRoutes = [
	{
		path: ROUTES.ROOT,
		element: <Navigate to={ROUTES.LOGIN} replace />,
	},
	{
		// ガード不要。AuthProviderの未認証リダイレクトより先行して本画面自身の
		// 交換・確認処理を完了させる例外パスのため、AuthLayout/AppLayoutの外に置く
		// （docs/detailed_design/screen/11_oauth_callback.md §1）
		path: ROUTES.OAUTH_CALLBACK,
		element: <OAuthCallbackPage />,
	},
	{
		element: <AuthLayout />,
		children: [
			{
				element: <RequireGuest />,
				children: [
					{
						path: ROUTES.LOGIN,
						element: <LoginPage />,
					},
					{
						path: ROUTES.REGISTER,
						element: <RegisterPage />,
					},
				],
			},
		],
	},
	// パスワード再設定・メール認証は認証状態に関わらず表示する公開画面のため、
	// RequireGuest/RequireAuthのいずれのガードにも含めない（各設計書§1参照）。
	{
		path: ROUTES.PASSWORD_FORGOT,
		element: <PasswordForgotPage />,
	},
	{
		path: ROUTES.PASSWORD_RESET,
		element: <PasswordResetPage />,
	},
	{
		path: ROUTES.VERIFY_EMAIL,
		element: <VerifyEmailPage />,
	},
	{
		element: <AppLayout />,
		children: [
			{
				element: <RequireAuth />,
				children: [
					{
						path: ROUTES.DASHBOARD,
						element: <DashboardPage />,
					},
					{
						path: ROUTES.PROJECT_PATTERN,
						element: <BoardPage />,
					},
					{
						path: ROUTES.TASK_PATTERN,
						element: <BoardPage />,
					},
					{
						path: ROUTES.SETTINGS,
						element: <SettingsPage />,
					},
				],
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
];

export const router = createBrowserRouter(appRoutes);
