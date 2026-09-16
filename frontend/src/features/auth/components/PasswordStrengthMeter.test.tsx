import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PasswordStrengthMeter, calcPasswordStrength } from "./PasswordStrengthMeter";

describe("calcPasswordStrength", () => {
	it("未入力は0を返す", () => {
		expect(calcPasswordStrength("")).toBe(0);
	});

	it("8文字未満は1を返す", () => {
		expect(calcPasswordStrength("Ab1!")).toBe(1);
	});

	it("8文字以上で1種類のみは1を返す", () => {
		expect(calcPasswordStrength("aaaaaaaa")).toBe(1);
	});

	it("8文字以上で2種類は2を返す", () => {
		expect(calcPasswordStrength("aaaaaaaa1")).toBe(2);
	});

	it("8文字以上で4種類は4を返す", () => {
		expect(calcPasswordStrength("Aa1!aaaa")).toBe(4);
	});
});

describe("PasswordStrengthMeter", () => {
	it("強度に応じたラベルを表示する", () => {
		render(<PasswordStrengthMeter password="Aa1!aaaa" />);
		expect(screen.getByText("強い")).toBeInTheDocument();
	});
});
