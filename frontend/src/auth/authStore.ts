import { create } from "zustand";

import type { AuthAdapter, TokenStore } from "../api/authAdapter";

export type AuthUserRole = "member" | "admin";

export type AuthUser = {
	id: string;
	role: AuthUserRole;
};

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type AuthState = {
	user: AuthUser | null;
	status: AuthStatus;
	accessToken: string | null;
	authAdapter: AuthAdapter | null;
};

const initialAuthState: AuthState = {
	user: null,
	status: "loading",
	accessToken: null,
	authAdapter: null,
};

export type AuthStore = AuthState & {
	setLoading: () => void;
	setAuthenticated: (user: AuthUser) => void;
	setUnauthenticated: () => void;
	setAccessToken: (accessToken: string | null) => void;
	clear: () => void;
	setAuthAdapter: (authAdapter: AuthAdapter) => void;
	reset: () => void;
};

export const useAuthStore = create<AuthStore>((set, get) => ({
	...initialAuthState,
	setLoading: () => set({ ...initialAuthState }),
	setAuthenticated: (user) => set({ user, status: "authenticated" }),
	setUnauthenticated: () => set({ user: null, status: "unauthenticated", accessToken: null }),
	setAccessToken: (accessToken) => set({ accessToken }),
	clear: () => {
		get().authAdapter?.onLogout();
		set({ user: null, status: "unauthenticated", accessToken: null });
	},
	setAuthAdapter: (authAdapter) => set({ authAdapter }),
	reset: () => set(initialAuthState),
}));

export const authTokenStore: TokenStore = {
	getAccessToken: () => useAuthStore.getState().accessToken,
	setAccessToken: (accessToken) => useAuthStore.getState().setAccessToken(accessToken),
};
