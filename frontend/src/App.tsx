import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { BoardPage } from "./features/board/BoardPage";
import { ROUTES } from "./routes";

const router = createBrowserRouter([
	{ path: ROUTES.ROOT, element: <main><h1>Cerberus</h1></main> },
	{ path: ROUTES.PROJECT_PATTERN, element: <BoardPage /> },
	{ path: ROUTES.TASK_PATTERN, element: <BoardPage /> },
]);

function App() {
	return <RouterProvider router={router} />;
}

export default App;
