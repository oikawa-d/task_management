import { RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, type AuthBootstrap } from "./auth/AuthProvider";
import { AuthFormsProvider, type AuthFormSlots } from "./features/auth/pages/authFormSlots";
import { SettingsFormsProvider, type SettingsFormSlots } from "./features/settings/pages/SettingsPage";
import { queryClient } from "./lib/queryClient";
import { router } from "./router";
import styles from "./App.module.css";

type AppProps = {
	bootstrap?: AuthBootstrap;
	settingsForms?: SettingsFormSlots;
	authForms?: AuthFormSlots;
};

function App({ bootstrap, settingsForms, authForms }: AppProps) {
	return (
		<div className={styles.app}>
		<QueryClientProvider client={queryClient}>
			<AuthProvider bootstrap={bootstrap}>
				<AuthFormsProvider slots={authForms}>
					<SettingsFormsProvider slots={settingsForms}>
						<RouterProvider router={router} />
					</SettingsFormsProvider>
				</AuthFormsProvider>
			</AuthProvider>
		</QueryClientProvider>
		</div>
	);
}

export default App;
