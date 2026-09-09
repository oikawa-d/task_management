import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SettingsFormsProvider, SettingsPage, type SettingsPageProps } from "./SettingsPage";

function renderPage(initialEntry = "/settings", props: SettingsPageProps = {}) {
	return render(
		<MemoryRouter initialEntries={[initialEntry]}>
			<SettingsPage {...props} />
		</MemoryRouter>,
	);
}

describe("SettingsPage", () => {
	it("プロフィール編集とパスワード変更のフォーム領域を表示する", () => {
		renderPage();

		expect(screen.getByRole("heading", { name: "アカウント設定" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "プロフィール" })).toBeInTheDocument();
		expect(screen.getByRole("form", { name: "プロフィール編集フォーム" })).toBeInTheDocument();
		fireEvent.click(screen.getByRole("tab", { name: "パスワード" }));
		expect(screen.getByRole("form", { name: "パスワード変更フォーム" })).toBeInTheDocument();
	});

	it("complete_profileクエリで案内バナーとプロフィールタブを初期表示する", () => {
		renderPage("/settings?complete_profile=1");

		expect(screen.getByRole("status")).toHaveTextContent("プロフィールを入力してください");
		expect(screen.getByRole("tab", { name: "プロフィール" })).toHaveAttribute(
			"aria-selected",
			"true",
		);
	});

	it("プロフィール入力済みの場合はcomplete_profileバナーを表示しない", () => {
		renderPage("/settings?complete_profile=1", { profileCompleted: true });

		expect(screen.queryByRole("status")).not.toBeInTheDocument();
	});

	it("タブを切り替えると選択中のパネルだけを表示する", () => {
		renderPage();

		fireEvent.click(screen.getByRole("tab", { name: "表示設定" }));

		expect(screen.getByRole("tabpanel")).toHaveAccessibleName("表示設定");
		expect(screen.queryByRole("form", { name: "プロフィール編集フォーム" })).not.toBeInTheDocument();
	});

	it("矢印キーでタブを移動し、選択中タブへフォーカスする", () => {
		renderPage();
		const profileTab = screen.getByRole("tab", { name: "プロフィール" });

		profileTab.focus();
		fireEvent.keyDown(profileTab, { key: "ArrowRight" });

		expect(screen.getByRole("tab", { name: "パスワード" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByRole("tab", { name: "パスワード" })).toHaveFocus();
	});

	it("クリックで選択したタブにフォーカスを保持する", () => {
		renderPage();

		const passwordTab = screen.getByRole("tab", { name: "パスワード" });
		fireEvent.click(passwordTab);

		expect(passwordTab).toHaveAttribute("aria-selected", "true");
		expect(passwordTab).toHaveFocus();
	});

	it("SettingsFormsProviderの実フォームslotを設定画面へ描画する", () => {
		render(
		<MemoryRouter initialEntries={["/settings"]}>
			<SettingsFormsProvider
				slots={{
					profile: ({ onSuccess }) => (
						<button type="button" onClick={() => onSuccess("プロフィールを更新しました")}>
							実プロフィールフォーム
						</button>
					),
				}}
			>
				<SettingsPage />
			</SettingsFormsProvider>
		</MemoryRouter>,
		);

		fireEvent.click(screen.getByRole("button", { name: "実プロフィールフォーム" }));
		expect(screen.getByRole("status")).toHaveTextContent("プロフィールを更新しました");
	});
});
