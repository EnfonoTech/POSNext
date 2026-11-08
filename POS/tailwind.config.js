import frappeUIPreset from "frappe-ui/tailwind";

// Numo brand: every upstream blue / indigo utility renders in the Numo teal
// scale, so the 500+ hard-coded classes follow the brand without touching
// the components (keeps upstream merges conflict-free).
const numoTeal = {
	50: "#eaf6f4",
	100: "#cdebe6",
	200: "#9dd6cd",
	300: "#66bcae",
	400: "#339e8e",
	500: "#0d8273",
	600: "#05685e",
	700: "#00544c",
	800: "#00403c",
	900: "#0a3431",
	950: "#04201e",
};

export default {
	presets: [frappeUIPreset],
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
	],
	theme: {
		extend: {
			// POS tokens (see :root in src/index.css); frappe-ui already owns ink/surface
			colors: {
				blue: numoTeal,
				indigo: numoTeal,
				pos: {
					ink: "var(--pos-ink)",
					muted: "var(--pos-ink-muted)",
					surface: "var(--pos-surface)",
					panel: "var(--pos-panel)",
					line: "var(--pos-line)",
					action: "var(--pos-action)",
					"action-hover": "var(--pos-action-hover)",
					"action-soft": "var(--pos-action-soft)",
					saving: "var(--pos-saving)",
					caution: "var(--pos-caution)",
					danger: "var(--pos-danger)",
				},
			},
			fontSize: {
				"pos-sm": ["var(--pos-text-sm)", { lineHeight: "1.35" }],
				"pos-md": ["var(--pos-text-md)", { lineHeight: "1.3" }],
				"pos-lg": ["var(--pos-text-lg)", { lineHeight: "1.25" }],
				"pos-xl": ["var(--pos-text-xl)", { lineHeight: "1.15" }],
			},
			minHeight: { target: "var(--pos-target)" },
			minWidth: { target: "var(--pos-target)" },
		},
	},
	plugins: [],
};
