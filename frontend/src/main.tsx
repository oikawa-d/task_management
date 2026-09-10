import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { authFormSlots } from "./features/auth/pages/connectedAuthForms";
import "./styles/tokens.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
	throw new Error("root element not found");
}

createRoot(rootElement).render(
	<StrictMode>
		<App authForms={authFormSlots} />
	</StrictMode>,
);
