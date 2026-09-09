import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, type AuthBootstrap } from "./auth/AuthProvider";
import { router } from "./router";

const queryClient = new QueryClient();

type AppProps = {
	bootstrap?: AuthBootstrap;
};

function App({ bootstrap }: AppProps) {
	return (
		<QueryClientProvider client={queryClient}>
			<AuthProvider bootstrap={bootstrap}>
				<RouterProvider router={router} />
			</AuthProvider>
		</QueryClientProvider>
	);
}

export default App;
