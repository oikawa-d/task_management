import { describe, expect, it } from "vitest";

import { getDaysInMonth } from "./BirthDateSelect";

describe("getDaysInMonth", () => {
	it("うるう年の2月は29日を返す", () => {
		expect(getDaysInMonth(2028, 2)).toBe(29);
	});

	it("平年の2月は28日を返す", () => {
		expect(getDaysInMonth(2027, 2)).toBe(28);
	});

	it("年または月が未選択のときは31を返す", () => {
		expect(getDaysInMonth(undefined, undefined)).toBe(31);
		expect(getDaysInMonth(2028, undefined)).toBe(31);
	});
});
