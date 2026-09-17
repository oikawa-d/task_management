import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const indexHtml = readFileSync(resolve(process.cwd(), "index.html"), "utf8");

describe("index.html", () => {
	it("指定されたCerberusアイコンをfaviconとして参照する", () => {
		expect(indexHtml).toContain('<link rel="icon" type="image/png" href="/cerberus-icon.png" />');
	});
});
