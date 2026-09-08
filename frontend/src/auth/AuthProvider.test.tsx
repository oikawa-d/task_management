import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "./AuthProvider";
import { useAuthStore } from "./authStore";

function AuthStateProbe() {
	const status = useAuthStore((state) => state.status);
	const user = useAuthStore((state) => state.user);

	return <output data-testid="auth-state">{`${status}:${user?.id ?? "none"}`}</output>;
}

describe("AuthProvider", () => {
	afterEach(() => {
		useAuthStore.getState().reset();
	});

	it("keeps the loading state until bootstrap resolves", async () => {
		let resolveBootstrap: (user: { id: string; role: "member" | "admin"; profileCompleted: boolean } | null) => void = () => {};
		const bootstrap = vi.fn(
			() => new Promise<{ id: string; role: "member" | "admin"; profileCompleted: boolean } | null>((resolve) => (resolveBootstrap = resolve)),
		);

		render(
			<AuthProvider bootstrap={bootstrap}>
				<AuthStateProbe />
			</AuthProvider>,
		);

		expect(screen.getByTestId("auth-state")).toHaveTextContent("loading:none");
		expect(bootstrap).toHaveBeenCalledOnce();

		resolveBootstrap({ id: "u1", role: "member", profileCompleted: false });

		await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("authenticated:u1"));
	});

	it("sets unauthenticated when bootstrap finds no active session", async () => {
		const bootstrap = vi.fn().mockResolvedValue(null);

		render(
			<AuthProvider bootstrap={bootstrap}>
				<AuthStateProbe />
			</AuthProvider>,
		);

		await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("unauthenticated:none"));
	});

	it("sets unauthenticated when bootstrap fails", async () => {
		const bootstrap = vi.fn().mockRejectedValue(new Error("auth bootstrap failed"));

		render(
			<AuthProvider bootstrap={bootstrap}>
				<AuthStateProbe />
			</AuthProvider>,
		);

		await waitFor(() => expect(screen.getByTestId("auth-state")).toHaveTextContent("unauthenticated:none"));
	});
});
