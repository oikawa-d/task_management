import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GoogleLoginButton, buildGoogleOAuthUrl } from "./GoogleLoginButton";

describe("GoogleLoginButton", () => {
	it("enabled=falseのとき描画されない", () => {
		render(<GoogleLoginButton enabled={false} />);
		expect(screen.queryByRole("button")).not.toBeInTheDocument();
	});

	it("enabled=trueのときクリックでOAuth開始URLへ遷移する", () => {
		// jsdomは実ナビゲーションを実装しないため、window.locationをテスト用に差し替えて遷移先URLの組み立てのみ検証する
		const originalLocation = window.location;
		const locationMock = { href: "" } as Location;
		Object.defineProperty(window, "location", { value: locationMock, writable: true, configurable: true });

		render(<GoogleLoginButton enabled />);
		fireEvent.click(screen.getByRole("button", { name: "Googleでログイン" }));

		expect(locationMock.href).toBe(buildGoogleOAuthUrl());

		Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true });
	});

	it("labelを指定するとボタン文言を上書きできる", () => {
		render(<GoogleLoginButton enabled label="Googleで新規登録" />);
		expect(screen.getByRole("button", { name: "Googleで新規登録" })).toBeInTheDocument();
	});
});
