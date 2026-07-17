// Global test setup for the dine-in-main-cart Vitest suite.
//
// The POS source calls the Frappe translation global `__(...)` at module scope
// (stores, composables). jsdom does not provide it, so define a passthrough.
// roundCurrency() consults `window.flt` when present; we deliberately leave it
// undefined so the util falls back to its own Banker's-rounding implementation
// (the production default), keeping hand-computed money-math assertions stable.

const passthroughTranslate = (str, _replace, ...args) => {
	if (typeof str !== "string") return str;
	return str;
};

globalThis.__ = passthroughTranslate;
if (typeof window !== "undefined") {
	window.__ = passthroughTranslate;
	// Minimal frappe stub in case a module references it defensively.
	window.frappe = window.frappe || { _messages: {}, boot: {} };
}
