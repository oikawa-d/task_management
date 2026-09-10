import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VerifyEmailPage } from "./VerifyEmailPage";

function renderPage(hash: string, props: Parameters<typeof VerifyEmailPage>[0] = {}) {
	window.history.replaceState(null, "", `/verify-email${hash}`);
	return render(<VerifyEmailPage {...props} />);
}

describe("VerifyEmailPage", () => {
	it("hash中のtokenを結果表示スロットへpropsとして渡す", async () => {
		let receivedToken: string | null | undefined;
		renderPage("#token=verify-token-123", {
			result: ({ token }) => {
				receivedToken = token;
				return <p>token: {token}</p>;
			},
		});

		expect(await screen.findByText("token: verify-token-123")).toBeInTheDocument();
		expect(receivedToken).toBe("verify-token-123");
	});

	it("token抽出後はURL・履歴からfragmentが除去される", async () => {
		renderPage("#token=should-not-leak");

		await screen.findByRole("status");

		expect(window.location.hash).toBe("");
		expect(window.location.href).not.toContain("should-not-leak");
	});

	it("token欠落時はnullを結果表示スロットへ渡し、既定表示では再送formを出す", async () => {
		const result = vi.fn(() => <p>stub</p>);
		renderPage("", { result });

		await screen.findByText("stub");

		expect(result).toHaveBeenCalledWith({ token: null });
	});

	it("token欠落時の既定表示では再送formを表示する", async () => {
		renderPage("");

		expect(await screen.findByRole("alert")).toHaveTextContent("リンクが不正です");
		expect(screen.getByRole("form", { name: "認証メール再送フォーム" })).toBeInTheDocument();
	});
});
