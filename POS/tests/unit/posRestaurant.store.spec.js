// TDD (pre-implementation) — Dine-in on the main cart.
// Spec: .pipeline/spec.md  §"posRestaurant.js (or posTables.js) — NEW … holds
//        activeTable" + Q3 (LOCKED: POS Table Session = presence marker) + Edge
//        Cases "Checkout clears the table draft", "Clearing/holding interaction",
//        "Page reload mid-order".
//
// Subject: a NEW Pinia store `@/stores/posRestaurant` exposing `usePOSRestaurantStore`.
// The store owns the table-context state so posCart stays clean. The LOCKED,
// low-ambiguity contract encoded here:
//   - `activeTable` state, null by default (retail / no table bound).
//   - `setActiveTable(table)` binds a table (presence marker).
//   - `clearActiveTable()` unbinds (checkout frees the table, cart clear resets it).
//
// ASSUMED API (documented in test-results.md): action names `setActiveTable` /
// `clearActiveTable`. If the implementation names them differently, this file is the
// single place to realign — the *behaviour* (bind → active; clear → null; retail
// default null) is the spec-locked contract.
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED — `@/stores/posRestaurant` does not exist.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

// Keep the store isolated from the heavy cart/draft stores it orchestrates. The
// store now statically imports posCart/posDrafts (spec: posRestaurant holds the
// open/switch orchestration), so the cart's IO layer (frappe-ui) must be stubbed
// for the module graph to load — these state-action tests never invoke the
// orchestration, so a bare stub is enough.
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), reload: vi.fn(), reset: vi.fn(), data: null, loading: false }),
}));

import { usePOSRestaurantStore } from "@/stores/posRestaurant";

beforeEach(() => {
	setActivePinia(createPinia());
});

describe("posRestaurant store — table-context presence marker (Q3)", () => {
	it("defaults activeTable to null (retail / no table bound)", () => {
		const store = usePOSRestaurantStore();
		expect(store.activeTable == null).toBe(true);
	});

	it("binds a table via setActiveTable", () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("TABLE-5");
		expect(store.activeTable).toBe("TABLE-5");
	});

	it("clears the binding via clearActiveTable (checkout / cart-clear frees the table)", () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("TABLE-5");
		store.clearActiveTable();
		expect(store.activeTable == null).toBe(true);
	});

	it("rebinding switches the active table to the new one", () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("TABLE-A");
		store.setActiveTable("TABLE-B");
		expect(store.activeTable).toBe("TABLE-B");
	});
});
