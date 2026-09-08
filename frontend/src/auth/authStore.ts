import { create } from "zustand";

export type AuthUserRole = "member" | "admin";

export type AuthUser = {
	id: string;
	role: AuthUserRole;
};

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type AuthState = {
	user: AuthUser | null;
	status: AuthStatus;
};

const initialAuthState: AuthState = {
	user: null,
	status: "loading",
};

export type AuthStore = AuthState & {
	reset: () => void;
};

export const useAuthStore = create<AuthStore>((set) => ({
	...initialAuthState,
	reset: () => set(initialAuthState),
}));
