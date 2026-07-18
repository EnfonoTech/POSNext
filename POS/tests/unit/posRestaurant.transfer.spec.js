// TDD (pre-implementation) — Feature 2: Table transfer (frontend store action).
//
// Spec: .pipeline/spec.md §"Feature 2":
//   posRestaurant.js — add transferTable(toTable): call
//   pos_next.api.restaurant.transfer_table; on ok re-tag current draft
//   (drafts.saveDraftInvoice(..., toTable)), setActiveTable(toTable),
//   setActiveSession(res.session); return {ok, reason}.
// §"Test Plan → Frontend": "posRestaurant.transfer.spec.js — transferTable
//   re-tags draft + sets active table/session on ok; returns reason on failure;
//   never throws on best-effort paths."
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED — store.transferTable is undefined,
// so invoking it throws (TypeError) / assertions fail.
//
// Peripheral stores + IO are stubbed so the posRestaurant module graph loads
// without the heavy cart/draft/frappe-ui stack; the real store carries the
// transfer behaviour. The server `call` is mocked and dispatched by method name.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

// --- server call mock (hoisted so the vi.mock factory can reference it) --------
const { callMock } = vi.hoisted(() => ({ callMock: vi.fn() }));
vi.mock("@/utils/apiWrapper", () => ({ call: callMock }));

// --- peripheral store / IO isolation ------------------------------------------
const saveDraftInvoiceMock = vi.fn(async () => ({ draft_id: "DRAFT-1" }));
const cartState = {
	invoiceItems: [{ item_code: "PIZZA", qty: 1, rate: 30, notes: "" }],
	customer: "Walk-in",
	posProfile: "Main POS",
	appliedOffers: [],
	currentDraftId: "DRAFT-1",
	isEmpty: false,
};
vi.mock("@/stores/posCart", () => ({ usePOSCartStore: () => cartState }));
vi.mock("@/stores/posDrafts", () => ({
	usePOSDraftsStore: () => ({ saveDraftInvoice: saveDraftInvoiceMock, findDraftByTable: vi.fn(), loadDraft: vi.fn() }),
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

beforeEach(() => {
	setActivePinia(createPinia());
	callMock.mockReset();
	saveDraftInvoiceMock.mockClear();
	cartState.currentDraftId = "DRAFT-1";
});

describe("posRestaurant.transferTable (Feature 2)", () => {
	it("moves the active table + session on backend success", async () => {
		callMock.mockResolvedValue({ session: "TBLSES-0007", to_table: "T-DST" });
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		store.setActiveSession("TBLSES-0007");

		const res = await store.transferTable("T-DST");

		expect(res.ok).toBe(true);
		// server called with the from/to pair
		expect(callMock).toHaveBeenCalledWith(
			"pos_next.api.restaurant.transfer_table",
			expect.objectContaining({ from_table: "T-SRC", to_table: "T-DST" }),
		);
		// local state rebinds to the target
		expect(store.activeTable).toBe("T-DST");
		expect(store.activeSession).toBe("TBLSES-0007");
	});

	it("re-tags the current draft to the target table", async () => {
		callMock.mockResolvedValue({ session: "TBLSES-0007", to_table: "T-DST" });
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		store.setActiveSession("TBLSES-0007");

		await store.transferTable("T-DST");

		expect(saveDraftInvoiceMock).toHaveBeenCalled();
		// the table argument (last positional) must be the new table
		const lastArgs = saveDraftInvoiceMock.mock.calls.at(-1);
		expect(lastArgs[lastArgs.length - 1]).toBe("T-DST");
	});

	it("returns a reason and does not rebind when no table is active", async () => {
		const store = usePOSRestaurantStore();
		// activeTable is null (retail / nothing bound)
		const res = await store.transferTable("T-DST");
		expect(res.ok).toBe(false);
		expect(res.reason).toBeTruthy();
		expect(callMock).not.toHaveBeenCalled();
		expect(store.activeTable == null).toBe(true);
	});

	it("rejects transferring a table onto itself", async () => {
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		const res = await store.transferTable("T-SRC");
		expect(res.ok).toBe(false);
		expect(callMock).not.toHaveBeenCalled();
		expect(store.activeTable).toBe("T-SRC");
	});

	it("returns a reason (never throws) and keeps the source binding on backend failure", async () => {
		callMock.mockRejectedValue(new Error("target occupied"));
		const store = usePOSRestaurantStore();
		store.setActiveTable("T-SRC");
		store.setActiveSession("TBLSES-0007");

		const res = await store.transferTable("T-DST");

		expect(res.ok).toBe(false);
		expect(res.reason).toBeTruthy();
		// source binding preserved — the transfer did not happen
		expect(store.activeTable).toBe("T-SRC");
		expect(store.activeSession).toBe("TBLSES-0007");
	});
});
