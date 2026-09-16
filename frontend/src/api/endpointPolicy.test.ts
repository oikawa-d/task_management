import { describe, expect, it } from "vitest";

const endpointSources = {
	...import.meta.glob("../features/**/*.{ts,tsx}", {
		eager: true,
		query: "?raw",
		import: "default",
	}),
	...import.meta.glob("../lib/api/**/*.ts", {
		eager: true,
		query: "?raw",
		import: "default",
	}),
} as Record<string, string>;

/*
 * /auth/config is intentionally fetched directly during bootstrap because the
 * auth adapter cannot be resolved before that response is available.
 */
describe("feature API endpoint policy", () => {
	it("does not bypass the shared fetchWithAuth client", () => {
		for (const [filename, source] of Object.entries(endpointSources)) {
			if (filename.includes(".test.")) continue;
			expect(source, filename).not.toMatch(/\bgetApiClient\s*\(/);
			expect(source, filename).not.toMatch(/(^|[^A-Za-z])fetch\s*\(/);
			expect(source, filename).not.toMatch(/Authorization\s*:/);
			expect(source, filename).not.toMatch(/X-CSRF-Token\s*:/i);
		}
	});
});
