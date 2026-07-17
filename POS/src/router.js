import { shiftState } from "@/composables/useShift";
import { userResource } from "@/data/user";
import { createRouter, createWebHistory } from "vue-router";
import { session } from "./data/session";

const routes = [
	{
		path: "/",
		// "/sell" is an alias so restaurant terminals can reach the retail sell
		// screen explicitly without tripping the floor-first redirect below.
		alias: "/sell",
		name: "POSSale",
		component: () => import("@/pages/POSSale.vue"),
	},
	{
		path: "/tables",
		name: "Tables",
		component: () => import("@/pages/Tables.vue"),
	},
	{
		path: "/kitchen",
		name: "Kitchen",
		component: () => import("@/pages/Kitchen.vue"),
	},
	{
		name: "Login",
		path: "/account/login",
		component: () => import("@/pages/Login.vue"),
	},
	// Catch-all route
	{
		path: "/:pathMatch(.*)*",
		redirect: "/",
	},
];

const router = createRouter({
	history: createWebHistory("/pos"),
	routes,
});

router.beforeEach((to, from, next) => {
	// Check authentication status (session.user is already set in main.js before app mount)
	const isLoggedIn = session.isLoggedIn;

	// Only log during development
	if (import.meta.env.DEV) {
		console.log(`[Router] ${to.name} (from: ${from.name || "initial"}), auth: ${isLoggedIn}`);
	}

	// Restaurant mode is a per-POS-Profile toggle (custom field on the open
	// shift's profile). On a full page load shiftState is still empty when this
	// guard first runs (check_opening_shift is async), so fall back to the
	// persisted shift cache in localStorage — it survives reloads and carries the
	// same profile doc, keeping the gate reliable instead of racy.
	let activeProfile = shiftState.value?.pos_profile || null;
	let shiftOpen = !!shiftState.value?.isOpen;
	if (!activeProfile) {
		try {
			const cached = JSON.parse(localStorage.getItem("pos_shift_data") || "{}");
			activeProfile = cached?.pos_profile || null;
			shiftOpen = shiftOpen || !!activeProfile;
		} catch (e) {
			/* ignore malformed cache */
		}
	}
	const isRestaurant = Number(activeProfile?.restaurant_mode) === 1;

	// Redirect logic
	if (to.name === "Login" && isLoggedIn) {
		next({ name: "POSSale" });
	} else if (to.name !== "Login" && !isLoggedIn) {
		next({ name: "Login" });
	} else if ((to.name === "Tables" || to.name === "Kitchen") && !isRestaurant) {
		// Retail profiles never see the restaurant screens.
		next({ name: "POSSale" });
	} else if (to.path === "/" && isRestaurant && shiftOpen) {
		// Floor-first: a restaurant terminal with an open shift lands on the
		// tables map. /sell (alias) still reaches the retail screen directly.
		next({ name: "Tables" });
	} else {
		next();
	}
});

export default router;
