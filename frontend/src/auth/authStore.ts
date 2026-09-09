import { create } from "zustand";

import type { AuthAdapter } from "../api/authAdapter";

export type AuthUserRole = "member" | "admin";

export type AuthUser = {
	id: string;
	role: AuthUserRole;
};

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type AuthState = {
	user: AuthUser | null;
	status: AuthStatus;
	authAdapter: AuthAdapter | null;
};

const initialAuthState: AuthState = {
	user: null,
	status: "loading",
	authAdapter: null,
};

export type AuthStore = AuthState & {
	setLoading: () => void;
	setAuthenticated: (user: AuthUser) => void;
	setUnauthenticated: () => void;
	clear: () => void;
	setAuthAdapter: (authAdapter: AuthAdapter) => void;
	reset: () => void;
};

export const useAuthStore = create<AuthStore>((set, get) => ({
	...initialAuthState,
	setLoading: () => set({ ...initialAuthState }),
	setAuthenticated: (user) => set({ user, status: "authenticated" }),
	setUnauthenticated: () => set({ user: null, status: "unauthenticated" }),
	clear: () => {
		get().authAdapter?.onLogout();
		set({ user: null, status: "unauthenticated" });
	},
	setAuthAdapter: (authAdapter) => set({ authAdapter }),
	reset: () => set(initialAuthState),
}));
