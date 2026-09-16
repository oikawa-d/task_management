import { describe, expect, it } from "vitest";

import { localDateTimeToUtc, utcToLocalDateTime } from "./dateTime";

describe("task detail date time conversion", () => {
	it("UTCの23:59相当をAPP_TIMEZONEの同日として表示する", () => {
		expect(utcToLocalDateTime("2026-09-09T14:59:00Z")).toBe("2026-09-09T23:59");
	});

	it("UTCの翌日境界をAPP_TIMEZONEの00:00として表示する", () => {
		expect(utcToLocalDateTime("2026-09-09T15:00:00Z")).toBe("2026-09-10T00:00");
	});

	it("APP_TIMEZONEの入力をUTCへ正規化する", () => {
		expect(localDateTimeToUtc("2026-09-10T00:00")).toBe("2026-09-09T15:00:00.000Z");
		expect(localDateTimeToUtc("2026-09-09T23:59")).toBe("2026-09-09T14:59:00.000Z");
	});
});
