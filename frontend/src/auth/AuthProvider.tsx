import { useEffect, type PropsWithChildren } from "react";

import { bootstrapAuth } from "./authBootstrap";
import type { AuthUser } from "./authStore";
import { useAuthStore } from "./authStore";

export type AuthBootstrap = () => Promise<AuthUser | null>;

type AuthProviderProps = PropsWithChildren<{
	bootstrap?: AuthBootstrap;
}>;

export function AuthProvider({ children, bootstrap = bootstrapAuth }: AuthProviderProps) {
	useEffect(() => {
		let isMounted = true;
		const store = useAuthStore.getState();
		store.setLoading();

		void bootstrap()
			.then((user) => {
				if (!isMounted) {
					return;
				}
				const nextStore = useAuthStore.getState();
				if (user) {
					nextStore.setAuthenticated(user);
				} else {
					nextStore.setUnauthenticated();
				}
			})
			.catch(() => {
				if (isMounted) {
					useAuthStore.getState().setUnauthenticated();
				}
			});

		return () => {
			isMounted = false;
		};
	}, [bootstrap]);

	return children;
}
