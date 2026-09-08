import "@testing-library/jest-dom/vitest";

import { act } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { useAuthStore } from "./auth/authStore";
import { SettingsFormsProvider } from "./features/settings/pages/SettingsPage";
import { appRoutes } from "./router";
import { ROUTES } from "./routes";

describe("アプリケーションルート", () => {
	afterEach(() => {
		act(() => {
			useAuthStore.getState().reset();
		});
	});

	it("認証済みユーザーが/settingsへアクセスするとAppLayout内に設定画面を表示する", async () => {
		act(() => {
			useAuthStore.setState({
				status: "authenticated",
				user: { id: "user-1", role: "member", profileCompleted: false },
			});
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [`${ROUTES.SETTINGS}?complete_profile=1`] });

		await act(async () => {
			render(
				<SettingsFormsProvider slots={{
					profile: ({ onSuccess }) => (
						<button type="button" onClick={() => onSuccess("プロフィールを更新しました")}>
							保存
						</button>
					),
				}}>
					<RouterProvider router={router} />
				</SettingsFormsProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "アカウント設定" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "設定" })).toHaveAttribute("href", ROUTES.SETTINGS);
		expect(screen.getByText("プロフィールを入力してください")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "保存" }));
		expect(screen.getByText("プロフィールを更新しました")).toBeInTheDocument();
	});

	it("設定ルートはauthStoreのprofileCompletedをバナー表示へ反映する", async () => {
		act(() => {
			useAuthStore.setState({
				status: "authenticated",
				user: { id: "user-1", role: "member", profileCompleted: true },
			});
		});
		const router = createMemoryRouter(appRoutes, { initialEntries: [`${ROUTES.SETTINGS}?complete_profile=1`] });

		await act(async () => {
			render(
				<SettingsFormsProvider>
					<RouterProvider router={router} />
				</SettingsFormsProvider>,
			);
		});

		expect(await screen.findByRole("heading", { name: "アカウント設定" })).toBeInTheDocument();
		expect(screen.queryByText("プロフィールを入力してください")).not.toBeInTheDocument();
	});
});
