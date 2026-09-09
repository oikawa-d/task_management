import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, type AuthBootstrap } from "./auth/AuthProvider";
import { SettingsFormsProvider, type SettingsFormSlots } from "./features/settings/pages/SettingsPage";
import { router } from "./router";

const queryClient = new QueryClient();

type AppProps = {
	bootstrap?: AuthBootstrap;
	settingsForms?: SettingsFormSlots;
};

function App({ bootstrap, settingsForms }: AppProps) {
	return (
		<QueryClientProvider client={queryClient}>
			<AuthProvider bootstrap={bootstrap}>
				<SettingsFormsProvider slots={settingsForms}>
					<RouterProvider router={router} />
				</SettingsFormsProvider>
			</AuthProvider>
		</QueryClientProvider>
	);
}

export default App;
