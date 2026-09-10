import "@testing-library/jest-dom/vitest";

import { act } from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ROUTES } from "../../../routes";
import { PasswordForgotPage } from "./PasswordForgotPage";

function renderPage(props: Parameters<typeof PasswordForgotPage>[0] = {}) {
	return render(
		<MemoryRouter initialEntries={[ROUTES.PASSWORD_FORGOT]}>
			<Routes>
				<Route path={ROUTES.PASSWORD_FORGOT} element={<PasswordForgotPage {...props} />} />
				<Route path={ROUTES.LOGIN} element={<h1>ログイン</h1>} />
			</Routes>
		</MemoryRouter>,
	);
}

describe("PasswordForgotPage", () => {
	it("初期表示ではフォームスロットとログインへ戻るリンクを表示する", () => {
		renderPage();

		expect(screen.getByRole("form", { name: "パスワード再設定要求フォーム" })).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "ログイン画面に戻る" })).toHaveAttribute(
			"href",
			ROUTES.LOGIN,
		);
	});

	it("フォームスロットのonSent呼び出しで送信完了メッセージへ表示を置き換える", async () => {
		renderPage();

		act(() => {
			screen
				.getByRole("form", { name: "パスワード再設定要求フォーム" })
				.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
		});

		expect(await screen.findByRole("status")).toHaveTextContent(
			"ご登録のメールアドレス宛にパスワード再設定用のメールを送信しました。",
		);
		expect(
			screen.queryByRole("form", { name: "パスワード再設定要求フォーム" }),
		).not.toBeInTheDocument();
	});

	it("差し込んだformスロットにonSentが渡され、呼び出すと送信完了表示になる", async () => {
		renderPage({
			form: ({ onSent }) => (
				<button type="button" onClick={onSent}>
					送信する
				</button>
			),
		});

		act(() => {
			screen.getByRole("button", { name: "送信する" }).click();
		});

		expect(await screen.findByRole("status")).toBeInTheDocument();
	});
});
