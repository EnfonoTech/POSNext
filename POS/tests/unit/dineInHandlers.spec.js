// Runtime coverage for the dine-in ORCHESTRATION handlers (fix round 3, Reviewer
// item 4). The round-2 specs covered the underlying utils (kot) + shared cart
// (posCart) + draft round-trip, but the orchestration itself was untested. That
// orchestration now lives in the posRestaurant store (spec: "posRestaurant holds …
// the open/switch orchestration"), so the POSSale.vue handlers are thin wrappers
// and the logic is driven directly here, exactly like dineIn.integration drives
// posCart:
//   * confirmModifier   — server delta-only pricing folded onto the cart base (base+delta),
//   * sendKitchen        — select unsent -> kot_send -> mark sent -> persist draft,
//                          + the no-table block (item 5) + the nothing-new no-op,
//   * openTable          — save-then-load switch A->B->A + the abort-on-save-failure
//                          data-loss guard,
//   * touchSession / settleSession / cancelSession — the Q3 presence marker lifecycle.
//
// Peripheral stores + IO are stubbed (as in dineIn.integration); the real posCart,
// posDrafts and posRestaurant + real utils/kot carry the behaviour. The server
// `call` is mocked and dispatched by method name.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

// --- server call mock (hoisted so the vi.mock factory can reference it) --------
const { callMock } = vi.hoisted(() => ({ callMock: vi.fn() }));
vi.mock("@/utils/apiWrapper", () => ({ call: callMock }));

// --- IO / peripheral isolation (mirrors dineIn.integration) -------------------
vi.mock("frappe-ui", () => ({
	createResource: () => ({
		submit: vi.fn(),
		fetch: vi.fn(),
		reload: vi.fn(),
		reset: vi.fn(),
		data: null,
		loading: false,
	}),
}));
vi.mock("@/utils/offline", () => ({ isOffline: () => false, getCachedItem: () => null }));
vi.mock("@/utils/offline/offlineState", () => ({ offlineState: { isOffline: false } }));
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({
		returnSerials: vi.fn(),
		reserveSerials: vi.fn(),
		releaseSerials: vi.fn(),
	}),
}));
vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("@/utils/stockValidator", () => ({
	shouldValidateItemStock: () => false,
	checkStockAvailability: () => ({ available: true }),
}));
vi.mock("@/utils/errorHandler", () => ({ parseError: (e) => e?.message || "error" }));
vi.mock("@/stores/posOffers", () => ({
	usePOSOffersStore: () => ({
		clearOneTimeContext: vi.fn(),
		updateCartSnapshot: vi.fn(),
		loadOneTimeContextForCustomer: vi.fn(),
	}),
}));
vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({ shouldEnforceStockValidation: () => false, settings: {} }),
}));
vi.mock("@/stores/posShift", () => ({
	usePOSShiftStore: () => ({ currentProfile: null, profileName: "Main POS" }),
}));

// In-memory draftManager (mirrors the real contract) for the draft round-trip.
const _drafts = [];
let _seq = 0;
vi.mock("@/utils/draftManager", () => ({
	saveDraft: vi.fn(async (invoiceData) => {
		_seq += 1;
		const draft = {
			id: _seq,
			draft_id: `DRAFT-${_seq}`,
			...JSON.parse(JSON.stringify(invoiceData || {})),
			created_at: new Date(Date.UTC(2026, 0, 1, 0, 0, _seq)).toISOString(),
		};
		_drafts.push(draft);
		return draft;
	}),
	updateDraft: vi.fn(async (draftId, invoiceData) => {
		const existing = _drafts.find((d) => d.draft_id === draftId);
		Object.assign(existing, JSON.parse(JSON.stringify(invoiceData || {})));
		return existing;
	}),
	getAllDrafts: vi.fn(async () =>
		[..._drafts].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
	),
	getDraftsCount: vi.fn(async () => _drafts.length),
	deleteDraft: vi.fn(async (draftId) => {
		const i = _drafts.findIndex((d) => d.draft_id === draftId);
		if (i >= 0) _drafts.splice(i, 1);
		return true;
	}),
}));

import { usePOSCartStore } from "@/stores/posCart";
import { usePOSDraftsStore } from "@/stores/posDrafts";
import { usePOSRestaurantStore } from "@/stores/posRestaurant";

function modifierLine({ base = 10, delta = 0, note = "", selection = {}, line_uid, sent = 0 }) {
	const rate = base + delta;
	return {
		item_code: "ESPRESSO",
		item_name: "Espresso",
		uom: "Nos",
		stock_uom: "Nos",
		conversion_factor: 1,
		rate,
		price_list_rate: rate,
		modifier_note: note,
		modifier_selection: selection,
		line_uid,
		sent_to_kitchen: sent,
	};
}

// Default server responses, dispatched by method name.
function defaultDispatch(method, args) {
	if (method.endsWith("get_modifier_selection")) return { delta: 5, note: "Large", validated: {} };
	if (method.endsWith("kot_send")) return { kot: "KOT-0001", status: "Open" };
	if (method.endsWith("get_session")) return { name: "SESS-1", table: args?.table };
	if (method.endsWith("session_settle")) return { already: false };
	if (method.endsWith("session_cancel")) return { status: "Cancelled" };
	return {};
}

let cart;
let restaurant;
beforeEach(() => {
	setActivePinia(createPinia());
	cart = usePOSCartStore();
	cart.setTaxInclusive(false);
	restaurant = usePOSRestaurantStore();
	_drafts.length = 0;
	_seq = 0;
	callMock.mockReset();
	callMock.mockImplementation(async (method, args) => defaultDispatch(method, args));
});

describe("posRestaurant.confirmModifier — server delta-only folded onto the base (base+delta)", () => {
	it("adds a line at price_list_rate === rate === base + serverDelta with modifier fields", async () => {
		const item = { item_code: "ESPRESSO", item_name: "Espresso", uom: "Nos", stock_uom: "Nos", conversion_factor: 1, price_list_rate: 10, rate: 10 };
		const res = await restaurant.confirmModifier(item, { Size: ["Large"] });
		expect(res.ok).toBe(true);
		expect(callMock).toHaveBeenCalledWith(
			"pos_next.api.restaurant.get_modifier_selection",
			expect.objectContaining({ item_code: "ESPRESSO" })
		);
		const line = cart.invoiceItems[0];
		expect(line.price_list_rate).toBe(15); // base 10 + delta 5
		expect(line.rate).toBe(15);
		expect(line.modifier_note).toBe("Large");
		expect(line.modifier_selection).toEqual({ Size: ["Large"] });
		expect(typeof line.line_uid).toBe("string");
		expect(line.line_uid.length).toBeGreaterThan(0);
		expect(line.sent_to_kitchen).toBe(0);
		expect(cart.subtotal).toBe(15);
	});

	it("propagates a pricing failure and adds nothing", async () => {
		callMock.mockRejectedValueOnce(new Error("boom"));
		const item = { item_code: "ESPRESSO", price_list_rate: 10, uom: "Nos", stock_uom: "Nos", conversion_factor: 1 };
		await expect(restaurant.confirmModifier(item, { Size: ["Large"] })).rejects.toThrow();
		expect(cart.invoiceItems).toHaveLength(0);
	});
});

describe("posRestaurant.sendKitchen — select -> mark -> persist", () => {
	it("fires unsent lines, marks them sent, and persists the table draft", async () => {
		restaurant.setActiveTable("TABLE-1");
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1" }), 1, false, null);

		const res = await restaurant.sendKitchen();
		expect(res).toEqual({ ok: true, kot: "KOT-0001" });

		const kotCall = callMock.mock.calls.find((c) => c[0].endsWith("kot_send"));
		expect(kotCall).toBeTruthy();
		expect(kotCall[1].table_label).toBe("TABLE-1");
		expect(kotCall[1].table).toBe("TABLE-1");
		expect(kotCall[1].items.map((i) => i.item_code)).toEqual(["ESPRESSO"]);
		expect(kotCall[1].items[0].notes).toBe("Large");

		// lines flipped to sent + stamped, and re-firing is a no-op
		expect(cart.invoiceItems.every((l) => l.sent_to_kitchen === 1)).toBe(true);
		expect(cart.invoiceItems[0].kot).toBe("KOT-0001");
		// persisted: a table draft now exists and currentDraftId points at it
		expect(cart.currentDraftId).toBeTruthy();
		const drafts = usePOSDraftsStore();
		const found = await drafts.findDraftByTable("TABLE-1");
		expect(found).toBeTruthy();
		expect(found.items[0].sent_to_kitchen).toBe(1);

		const again = await restaurant.sendKitchen();
		expect(again).toEqual({ ok: false, reason: "nothing-new" });
	});

	it("blocks Send-to-Kitchen when no table is bound (item 5) and never calls kot_send", async () => {
		restaurant.clearActiveTable();
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1" }), 1, false, null);
		const res = await restaurant.sendKitchen();
		expect(res).toEqual({ ok: false, reason: "no-table" });
		expect(callMock.mock.calls.some((c) => c[0].endsWith("kot_send"))).toBe(false);
		// the line stays unsent (nothing was fired, so nothing can be lost/re-fired)
		expect(cart.invoiceItems[0].sent_to_kitchen).toBe(0);
	});

	it("returns nothing-new when there are no unsent lines", async () => {
		restaurant.setActiveTable("TABLE-1");
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1", sent: 1 }), 1, false, null);
		const res = await restaurant.sendKitchen();
		expect(res).toEqual({ ok: false, reason: "nothing-new" });
		expect(callMock.mock.calls.some((c) => c[0].endsWith("kot_send"))).toBe(false);
	});
});

describe("posRestaurant.openTable — save-then-load switch + data-loss guard", () => {
	it("restores each table's exact lines across A -> B -> A", async () => {
		await restaurant.openTable("A", { online: false });
		cart.addItem(modifierLine({ delta: 0, note: "Regular", selection: { Size: ["Regular"] }, line_uid: "uA" }), 1, false, null);

		await restaurant.openTable("B", { online: false });
		expect(cart.invoiceItems).toHaveLength(0); // fresh empty cart for B
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "uB" }), 1, false, null);

		const res = await restaurant.openTable("A", { online: false });
		expect(res.ok).toBe(true);
		expect(res.loaded).toBeTruthy();
		expect(restaurant.activeTable).toBe("A");
		expect(cart.invoiceItems).toHaveLength(1);
		expect(cart.invoiceItems[0].line_uid).toBe("uA");
		expect(cart.invoiceItems[0].price_list_rate).toBe(10);
	});

	it("aborts the switch and preserves the current cart when the pre-save fails", async () => {
		await restaurant.openTable("A", { online: false });
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "uA" }), 1, false, null);

		const drafts = usePOSDraftsStore();
		vi.spyOn(drafts, "saveDraftInvoice").mockResolvedValueOnce(null);

		const res = await restaurant.openTable("B", { online: false });
		expect(res).toEqual({ ok: false, reason: "save-failed" });
		// switch aborted: still on A, A's cart intact (no data loss)
		expect(restaurant.activeTable).toBe("A");
		expect(cart.invoiceItems).toHaveLength(1);
		expect(cart.invoiceItems[0].line_uid).toBe("uA");
	});

	it("is a no-op when re-opening the already-active table", async () => {
		await restaurant.openTable("A", { online: false });
		const res = await restaurant.openTable("A", { online: false });
		expect(res).toEqual({ ok: false, reason: "same-table" });
	});
});

describe("posRestaurant — Q3 presence session lifecycle", () => {
	it("touches (creates) the session on open and records its name", async () => {
		const res = await restaurant.openTable("A", { online: true });
		expect(res.ok).toBe(true);
		expect(restaurant.activeSession).toBe("SESS-1");
		const getSessionCall = callMock.mock.calls.find((c) => c[0].endsWith("get_session"));
		expect(getSessionCall[1]).toMatchObject({ table: "A", create: 1 });
	});

	it("skips the session server call when offline (online:false)", async () => {
		await restaurant.openTable("A", { online: false });
		expect(restaurant.activeSession).toBeNull();
		expect(callMock.mock.calls.some((c) => c[0].endsWith("get_session"))).toBe(false);
	});

	it("settles the session against the invoice on checkout, then clears it", async () => {
		await restaurant.openTable("A", { online: true });
		expect(restaurant.activeSession).toBe("SESS-1");
		callMock.mockClear();
		await restaurant.settleSession("SINV-100");
		expect(callMock).toHaveBeenCalledWith(
			"pos_next.api.restaurant.session_settle",
			expect.objectContaining({ session: "SESS-1", sales_invoice: "SINV-100" })
		);
		expect(restaurant.activeSession).toBeNull();
	});

	it("cancels the session on explicit clear, then clears it", async () => {
		await restaurant.touchSession("A", true);
		expect(restaurant.activeSession).toBe("SESS-1");
		callMock.mockClear();
		await restaurant.cancelSession();
		expect(callMock).toHaveBeenCalledWith(
			"pos_next.api.restaurant.session_cancel",
			{ session: "SESS-1" }
		);
		expect(restaurant.activeSession).toBeNull();
	});

	it("settleSession / cancelSession are no-ops when no session is held (retail)", async () => {
		await restaurant.settleSession("SINV-1");
		await restaurant.cancelSession();
		expect(callMock.mock.calls.length).toBe(0);
	});
});
