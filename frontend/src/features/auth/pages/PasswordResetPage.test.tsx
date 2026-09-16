import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ROUTES } from "../../../routes";
import { PasswordResetPage } from "./PasswordResetPage";

function renderPage(hash: string, props: Parameters<typeof PasswordResetPage>[0] = {}) {
	window.history.replaceState(null, "", `${ROUTES.PASSWORD_RESET}${hash}`);
	return render(
		<MemoryRouter initialEntries={[`${ROUTES.PASSWORD_RESET}${hash}`]}>
			<Routes>
				<Route path={ROUTES.PASSWORD_RESET} element={<PasswordResetPage {...props} />} />
				<Route path={ROUTES.PASSWORD_FORGOT} element={<h1>パスワードをお忘れの方</h1>} />
			</Routes>
		</MemoryRouter>,
	);
}

describe("PasswordResetPage", () => {
	afterEach(() => {
		window.history.replaceState(null, "", "/");
	});

	it("hash中のtokenをフォームスロットへpropsとして渡す", async () => {
		let receivedToken: string | undefined;
		renderPage("#token=reset-token-123", {
			form: ({ token }) => {
				receivedToken = token;
				return <form aria-label="passed">token: {token}</form>;
			},
		});

		expect(await screen.findByText("token: reset-token-123")).toBeInTheDocument();
		expect(receivedToken).toBe("reset-token-123");
	});

	it("token抽出後はURL・履歴からfragmentが除去される", async () => {
		renderPage("#token=should-not-leak");

		await screen.findByRole("form", { name: "パスワード再設定フォーム" });

		expect(window.location.hash).toBe("");
		expect(window.location.href).not.toContain("should-not-leak");
	});

	it("token欠落時は再要求導線のみを表示しフォームスロットを呼ばない", async () => {
		const form = vi.fn();
		renderPage("", { form });

		expect(await screen.findByRole("alert")).toHaveTextContent(
			"リンクの有効期限が切れているか、既に使用済みです",
		);
		expect(screen.getByRole("link", { name: "もう一度リセットを申請する" })).toHaveAttribute(
			"href",
			ROUTES.PASSWORD_FORGOT,
		);
		expect(form).not.toHaveBeenCalled();
	});
});
