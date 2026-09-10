import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, type AuthBootstrap } from "./auth/AuthProvider";
import { AuthFormsProvider, type AuthFormSlots } from "./features/auth/pages/authFormSlots";
import { SettingsFormsProvider, type SettingsFormSlots } from "./features/settings/pages/SettingsPage";
import { router } from "./router";

const queryClient = new QueryClient();

type AppProps = {
	bootstrap?: AuthBootstrap;
	settingsForms?: SettingsFormSlots;
	authForms?: AuthFormSlots;
};

function App({ bootstrap, settingsForms, authForms }: AppProps) {
	return (
		<QueryClientProvider client={queryClient}>
			<AuthProvider bootstrap={bootstrap}>
				<AuthFormsProvider slots={authForms}>
					<SettingsFormsProvider slots={settingsForms}>
						<RouterProvider router={router} />
					</SettingsFormsProvider>
				</AuthFormsProvider>
			</AuthProvider>
		</QueryClientProvider>
	);
}

export default App;
