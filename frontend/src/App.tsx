import { RouterProvider } from "react-router-dom";

import { AuthProvider, type AuthBootstrap } from "./auth/AuthProvider";
import { SettingsFormsProvider, type SettingsFormSlots } from "./features/settings/pages/SettingsPage";
import { router } from "./router";

type AppProps = {
	bootstrap?: AuthBootstrap;
	settingsForms?: SettingsFormSlots;
};

function App({ bootstrap, settingsForms }: AppProps) {
	return (
		<AuthProvider bootstrap={bootstrap}>
			<SettingsFormsProvider slots={settingsForms}>
				<RouterProvider router={router} />
			</SettingsFormsProvider>
		</AuthProvider>
	);
}

export default App;
