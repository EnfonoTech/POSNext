// Regression (F1) — the modifier-group map must live in the posRestaurant store,
// not an SFC-local ref, so it survives POSSale remounts. Before the fix the map was
// reset to {} on every remount and the modifier picker silently stopped opening
// after the first table. This locks: load populates the map, a re-read of the
// singleton store still sees it (the "remount" case), lookups resolve, and a
// non-forced reload does not hit the server again.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const callMock = vi.fn();
vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => callMock(...args) }));
// posRestaurant statically imports posCart/posDrafts → frappe-ui; stub so the graph loads.
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), reload: vi.fn(), reset: vi.fn(), data: null, loading: false }),
}));

import { usePOSRestaurantStore } from "@/stores/posRestaurant";

const MAP = {
	ESPRESSO: [{ group_name: "Size", selection_type: "Single", options: [{ label: "Large", price_delta: 5 }] }],
};

beforeEach(() => {
	setActivePinia(createPinia());
	callMock.mockReset();
	callMock.mockResolvedValue(MAP);
});

describe("posRestaurant modifier-group map (F1 — survives remount)", () => {
	it("defaults to an empty map (no groups until loaded)", () => {
		const store = usePOSRestaurantStore();
		expect(store.modifierGroupsFor("ESPRESSO")).toEqual([]);
	});

	it("loadModifierGroupsMap populates the map from the server", async () => {
		const store = usePOSRestaurantStore();
		await store.loadModifierGroupsMap();
		expect(callMock).toHaveBeenCalledWith("pos_next.api.restaurant.get_item_modifiers");
		expect(store.modifierGroupsFor("ESPRESSO")).toHaveLength(1);
		expect(store.modifierGroupsFor("NOPE")).toEqual([]);
	});

	it("the map persists on the singleton across a simulated remount (re-read of the store)", async () => {
		await usePOSRestaurantStore().loadModifierGroupsMap();
		// A POSSale remount re-reads the same Pinia singleton — the map is still there,
		// so the picker still opens (this is the regression the SFC-local ref broke).
		const afterRemount = usePOSRestaurantStore();
		expect(afterRemount.modifierGroupsFor("ESPRESSO")).toHaveLength(1);
	});

	it("does not re-hit the server when already populated (non-forced)", async () => {
		const store = usePOSRestaurantStore();
		await store.loadModifierGroupsMap();
		await store.loadModifierGroupsMap();
		expect(callMock).toHaveBeenCalledTimes(1);
	});

	it("force reloads even when populated", async () => {
		const store = usePOSRestaurantStore();
		await store.loadModifierGroupsMap();
		await store.loadModifierGroupsMap({ force: true });
		expect(callMock).toHaveBeenCalledTimes(2);
	});

	it("is best-effort: a server failure leaves an empty map, not a throw", async () => {
		callMock.mockRejectedValueOnce(new Error("offline"));
		const store = usePOSRestaurantStore();
		await expect(store.loadModifierGroupsMap()).resolves.toBeDefined();
		expect(store.modifierGroupsFor("ESPRESSO")).toEqual([]);
	});
});
