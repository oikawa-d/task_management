import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { coverageConfigDefaults } from "vitest/config";

export default defineConfig({
	plugins: [react()],
	test: {
		environment: "jsdom",
		globals: true,
		coverage: {
			provider: "v8",
			// main.tsxはReactDOMのマウント処理のみを行うエントリポイントであり、
			// ロジックを含まずテスト対象として意味を持たないためカバレッジ対象から除外する。
			exclude: [...coverageConfigDefaults.exclude, "src/main.tsx"],
			thresholds: {
				statements: 70,
				branches: 70,
				functions: 70,
				lines: 70,
			},
		},
	},
});
