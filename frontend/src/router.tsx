import { createBrowserRouter, createMemoryRouter, Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";

import { BoardPage } from "./features/board/BoardPage";
import { ROUTES } from "./routes";

function LandingPage() {
	return <Navigate to={ROUTES.LOGIN} replace />;
}

function LoginPlaceholder() {
	return (
		<main>
			<h1>Cerberus</h1>
		</main>
	);
}

export const appRoutes: RouteObject[] = [
	{ path: ROUTES.ROOT, element: <LandingPage /> },
	{ path: ROUTES.LOGIN, element: <LoginPlaceholder /> },
	{ path: ROUTES.PROJECT_PATTERN, element: <BoardPage /> },
	{ path: ROUTES.TASK_PATTERN, element: <BoardPage /> },
];

export function createAppRouter(initialEntries?: string[]) {
	if (initialEntries) {
		return createMemoryRouter(appRoutes, { initialEntries });
	}
	return createBrowserRouter(appRoutes);
}
