import { RouterProvider } from "react-router-dom";

import { AuthProvider, type AuthBootstrap } from "./auth/AuthProvider";
import { router } from "./router";

type AppProps = {
	bootstrap?: AuthBootstrap;
};

function App({ bootstrap }: AppProps) {
	return (
		<AuthProvider bootstrap={bootstrap}>
			<RouterProvider router={router} />
		</AuthProvider>
	);
}

export default App;
