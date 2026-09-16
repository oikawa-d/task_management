import { create } from "zustand";

import type { AuthAdapter } from "../api/authAdapter";
import { authTokenStore } from "./tokenStore";

export type AuthUserRole = "member" | "admin";

export type AuthUser = {
	id: string;
	role: AuthUserRole;
	display_name?: string;
};

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type AuthState = {
	user: AuthUser | null;
	status: AuthStatus;
	authAdapter: AuthAdapter | null;
	/** GET /auth/config の google_login_enabled。AuthProvider起動時（authBootstrap）に設定される */
	googleLoginEnabled: boolean;
};

const initialAuthState: AuthState = {
	user: null,
	status: "loading",
	authAdapter: null,
	googleLoginEnabled: false,
};

export type AuthStore = AuthState & {
	setLoading: () => void;
	setAuthenticated: (user: AuthUser) => void;
	setUnauthenticated: () => void;
	updateUser: (user: Partial<AuthUser>) => void;
	clear: () => void;
	setAuthAdapter: (authAdapter: AuthAdapter) => void;
	setGoogleLoginEnabled: (enabled: boolean) => void;
	reset: () => void;
};

export const useAuthStore = create<AuthStore>((set, get) => ({
	...initialAuthState,
	setLoading: () => {
		authTokenStore.setAccessToken(null);
		set({ ...initialAuthState });
	},
	setAuthenticated: (user) => set({ user, status: "authenticated" }),
	setUnauthenticated: () => {
		get().authAdapter?.onLogout();
		authTokenStore.setAccessToken(null);
		set({ user: null, status: "unauthenticated" });
	},
	updateUser: (user) => set((state) => ({ user: state.user ? { ...state.user, ...user } : state.user })),
	clear: () => {
		get().authAdapter?.onLogout();
		authTokenStore.setAccessToken(null);
		set({ user: null, status: "unauthenticated" });
	},
	setAuthAdapter: (authAdapter) => set({ authAdapter }),
	setGoogleLoginEnabled: (googleLoginEnabled) => set({ googleLoginEnabled }),
	reset: () => {
		authTokenStore.setAccessToken(null);
		set(initialAuthState);
	},
}));

export { authTokenStore } from "./tokenStore";
