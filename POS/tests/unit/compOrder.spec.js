// TDD (pre-implementation) — Feature 1: Complimentary / Void (frontend orchestration).
//
// Spec: .pipeline/spec.md §"Feature 1 (frontend)":
//   POSSale.vue handleCompOrder(payload) "calls submit_complimentary_order with
//   cartStore.invoiceItems mapped to {item_code, qty, rate, notes}; on success
//   clear cart + restaurantStore.cancelSession() + discard draft".
// §"Test Plan → Frontend": "Comp payload mapping — cart lines → {item_code, qty,
//   rate, notes} shape; dialog blocks confirm without a reason."
//
// ASSUMED API (documented in test-results.md, single realignment point): the
// dine-in ORCHESTRATION lives in the posRestaurant store (see
// dineInHandlers.spec.js header: "orchestration now lives in the posRestaurant
// store … the POSSale.vue handlers are thin wrappers"). So the comp submit is a
// store action `submitCompOrder({ reason, reason_note })`. If the implementation
// names it differently, realign here — the spec-locked *behaviour* is:
//   - a reason is REQUIRED (no reason -> no server call);
//   - cart lines map to {item_code, qty, rate, notes};
//   - on success the cart is cleared and the presence session is cancelled;
//   - it never creates / calls a Sales-Invoice endpoint.
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED — store.submitCompOrder is undefined.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const { callMock } = vi.hoisted(() => ({ callMock: vi.fn() }));
vi.mock("@/utils/apiWrapper", () => ({ call: callMock }));

const clearCartMock = vi.fn();
const cartState = {
	invoiceItems: [
		{ item_code: "PIZZA", qty: 2, rate: 30, notes: "extra cheese", sent_to_kitchen: 1, line_uid: "a" },
		{ item_code: "COLA", qty: 1, rate: 5, notes: "", line_uid: "b" },
	],
	customer: "Walk-in",
	posProfile: "Main POS",
	appliedOffers: [],
	currentDraftId: "DRAFT-9",
	isEmpty: false,
	clearCart: clearCartMock,
};
vi.mock("@/stores/posCart", () => ({ usePOSCartStore: () => cartState }));
vi.mock("@/stores/posDrafts", () => ({
	usePOSDraftsStore: () => ({
		saveDraftInvoice: vi.fn(),
		findDraftByTable: vi.fn(),
		loadDraft: vi.fn(),
		discardDraft: vi.fn(),
		deleteDraft: vi.fn(),
	}),
}));
vi.mock("@/stores/posShift", () => ({
	usePOSShiftStore: () => ({ currentProfile: null, profileName: "Main POS", isRestaurant: true }),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("frappe-ui", () => ({
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), reload: vi.fn(), reset: vi.fn(), data: null, loading: false }),
}));

import { usePOSRestaurantStore } from "@/stores/posRestaurant";

function callsTo(method) {
	return callMock.mock.calls.filter((c) => c[0] === method);
}

beforeEach(() => {
	setActivePinia(createPinia());
	callMock.mockReset();
	callMock.mockResolvedValue({ comp_order: "COMP-0001", status: "Pending" });
	clearCartMock.mockClear();
});

describe("posRestaurant.submitCompOrder — complimentary / void (Feature 1)", () => {
	it("blocks confirm without a reason (no server call)", async () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		const res = await store.submitCompOrder({ reason: "" });
		expect(res.ok).toBe(false);
		expect(callsTo("pos_next.api.restaurant.submit_complimentary_order")).toHaveLength(0);
	});

	it("maps cart lines to {item_code, qty, rate, notes} and passes the reason", async () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		await store.submitCompOrder({ reason: "Staff Meal", reason_note: "shift crew" });

		const submits = callsTo("pos_next.api.restaurant.submit_complimentary_order");
		expect(submits).toHaveLength(1);
		const payload = submits[0][1];
		expect(payload.reason).toBe("Staff Meal");
		expect(payload.items).toHaveLength(2);
		// exact mapping shape — item_code / qty / rate / notes only
		expect(payload.items[0]).toEqual(
			expect.objectContaining({ item_code: "PIZZA", qty: 2, rate: 30, notes: "extra cheese" }),
		);
		expect(payload.items[1]).toEqual(
			expect.objectContaining({ item_code: "COLA", qty: 1, rate: 5, notes: "" }),
		);
	});

	it("clears the cart and cancels the presence session on success", async () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		store.setActiveSession("TBLSES-0007");

		const res = await store.submitCompOrder({ reason: "Wastage / Spillage" });

		expect(res.ok).toBe(true);
		expect(clearCartMock).toHaveBeenCalled();
		// presence session cancelled (Q3 marker) -> cleared locally
		expect(store.activeSession == null).toBe(true);
	});

	it("never routes a comp through a Sales-Invoice endpoint", async () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		await store.submitCompOrder({ reason: "Management" });

		const invoiceCalls = callMock.mock.calls.filter(
			(c) => /submit_invoice|update_invoice|sales_invoice/i.test(String(c[0])),
		);
		expect(invoiceCalls).toHaveLength(0);
	});
});
