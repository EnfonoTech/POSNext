import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
	resolve: {
		alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
	},
	test: {
		// jsdom, not node: printInvoice's happy path prints through a real
		// iframe (printViaIframe), so it needs a document to append one to.
		environment: "jsdom",
		include: ["src/**/*.test.js"],
	},
});
