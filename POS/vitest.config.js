import path from "node:path";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// Standalone Vitest config for the dine-in-main-cart test suite.
// Kept separate from vite.config.js so the PWA / frappe-ui build plugins do not
// run under the test harness. SFCs in this project use explicit `vue` imports,
// so the plain @vitejs/plugin-vue transform is sufficient (no auto-import plugin).
export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	test: {
		environment: "jsdom",
		globals: true,
		setupFiles: ["./tests/setup.js"],
		include: ["tests/**/*.{test,spec}.{js,ts}"],
	},
});
