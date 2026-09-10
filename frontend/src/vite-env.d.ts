/// <reference types="vite/client" />

interface ImportMetaEnv {
	readonly VITE_API_BASE_URL?: string;
	readonly VITE_NOTIFICATION_POLL_INTERVAL_MS?: string;
	readonly VITE_USER_NAME_MAX_LENGTH?: string;
	readonly VITE_PASSWORD_MIN_LENGTH?: string;
}

interface ImportMeta {
	readonly env: ImportMetaEnv;
}

declare module "*.module.css" {
	const classes: { readonly [key: string]: string };
	export default classes;
}
