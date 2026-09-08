import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProfileForm } from "./ProfileForm";
import type { ProfileFormValues } from "./types";

const initialValues: ProfileFormValues = {
	last_name: "山田",
	first_name: "太郎",
	last_name_kana: "ヤマダ",
	first_name_kana: "タロウ",
	birth_date: "1990-01-01",
};

describe("ProfileForm", () => {
	it("変更されたプロフィールだけを送信し、成功メッセージを表示する", async () => {
		const onSubmit = vi.fn().mockResolvedValue(undefined);
		render(<ProfileForm initialValues={initialValues} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("姓"), { target: { value: "佐藤" } });
		await waitFor(() => expect(screen.getByRole("button", { name: "プロフィールを保存" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "プロフィールを保存" }));

		await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ last_name: "佐藤" }));
		expect(await screen.findByRole("status")).toHaveTextContent("プロフィールを更新しました");
	});

	it("不正なフリガナでは保存できず、エラーを表示する", async () => {
		const onSubmit = vi.fn();
		render(<ProfileForm initialValues={initialValues} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("姓カナ"), { target: { value: "山田" } });

		await waitFor(() => expect(screen.getByRole("button", { name: "プロフィールを保存" })).toBeDisabled());
		expect(await screen.findByText("ひらがな・カタカナ・数字のみで入力してください")).toBeInTheDocument();
		expect(onSubmit).not.toHaveBeenCalled();
	});

	it("APIのフィールドエラーを該当項目に表示する", async () => {
		const onSubmit = vi.fn().mockRejectedValue({
			details: [{ field: "first_name", message: "この名前は使用できません" }],
		});
		render(<ProfileForm initialValues={initialValues} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("名"), { target: { value: "花子" } });
		await waitFor(() => expect(screen.getByRole("button", { name: "プロフィールを保存" })).not.toBeDisabled());
		fireEvent.click(screen.getByRole("button", { name: "プロフィールを保存" }));

		expect(await screen.findByText("この名前は使用できません")).toBeInTheDocument();
	});

	it("未来の生年月日を入力すると保存できない", async () => {
		const onSubmit = vi.fn();
		render(<ProfileForm initialValues={initialValues} onSubmit={onSubmit} />);

		fireEvent.change(screen.getByLabelText("生年月日"), { target: { value: "2999-01-01" } });

		expect(await screen.findByText("未来の日付は指定できません")).toBeInTheDocument();
		await waitFor(() => expect(screen.getByRole("button", { name: "プロフィールを保存" })).toBeDisabled());
	});
});
