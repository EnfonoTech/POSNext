// Integration coverage for the WIRED dine-in path (fix round 2, Reviewer item 5).
//
// The other specs exercise isolated modules (useInvoice, kot, posDrafts,
// ModifierDialog). This one drives the real posCart store — the money-critical
// shared cart the feature actually mutates — end-to-end:
//   * base+delta money-math through the real add flow (posCart.addItem),
//   * line_uid split/merge + line_uid-addressed qty/remove in posCart,
//   * send-to-kitchen selection + marking applied to the live cart (utils/kot),
//   * draft round-trip WITH a table tag (posCart-built lines -> posDrafts),
//   * retail no-op: same add/remove path with no modifier context stays byte-for-byte.
//
// posCart pulls in many peripheral stores; only the real cart math (useInvoice),
// the real posRestaurant store, real posDrafts and real utils/kot matter here, so
// the peripheral stores + IO are stubbed. The offer watcher is debounced, so it
// never fires synchronously in these tests.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

// --- IO / peripheral isolation ------------------------------------------------
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
	usePOSShiftStore: () => ({ currentProfile: null }),
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
import { usePOSRestaurantStore } from "@/stores/posRestaurant";
import { usePOSDraftsStore } from "@/stores/posDrafts";
import { markCartLinesSent, selectUnsentKotItems } from "@/utils/kot";

// Mirrors handleModifierConfirm's output: base rate + server delta folded into
// price_list_rate === rate, plus the modifier fields + a fresh line_uid.
function modifierLine({ base = 10, delta, note, selection, line_uid }) {
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
		sent_to_kitchen: 0,
	};
}

function retailLine(overrides = {}) {
	return {
		item_code: "WATER",
		item_name: "Water",
		uom: "Nos",
		stock_uom: "Nos",
		conversion_factor: 1,
		rate: 2,
		price_list_rate: 2,
		...overrides,
	};
}

let cart;
beforeEach(() => {
	setActivePinia(createPinia());
	cart = usePOSCartStore();
	cart.setTaxInclusive(false); // no-tax so subtotal == sum(rate*qty)
});

describe("posCart.addItem — base+delta money-math + line construction (wired flow)", () => {
	it("adds a modifier line at price_list_rate === rate === base + delta and reflects it in subtotal", () => {
		cart.addItem(
			modifierLine({ base: 10, delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1" }),
			2,
			false,
			null
		);
		const line = cart.invoiceItems[0];
		expect(line.price_list_rate).toBe(15);
		expect(line.rate).toBe(15);
		expect(line.modifier_note).toBe("Large");
		expect(line.line_uid).toBe("u-1");
		expect(line.sent_to_kitchen).toBe(0);
		expect(cart.subtotal).toBe(30); // 15 × 2
	});
});

describe("posCart — line_uid split / merge", () => {
	it("splits same item+uom into distinct lines for different modifier selections", () => {
		cart.addItem(modifierLine({ delta: 0, note: "Regular", selection: { Size: ["Regular"] }, line_uid: "u-1" }), 1, false, null);
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-2" }), 1, false, null);
		expect(cart.invoiceItems).toHaveLength(2);
		expect(cart.subtotal).toBe(25); // 10 + 15
	});

	it("merges (increments qty) same item+uom with the SAME selection, keeping the original line_uid", () => {
		const sel = { Size: ["Large"] };
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: sel, line_uid: "u-1" }), 1, false, null);
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: sel, line_uid: "u-2" }), 1, false, null);
		expect(cart.invoiceItems).toHaveLength(1);
		expect(cart.invoiceItems[0].quantity).toBe(2);
		expect(cart.invoiceItems[0].line_uid).toBe("u-1");
		expect(cart.subtotal).toBe(30);
	});
});

describe("posCart — line_uid-addressed qty change / removal", () => {
	beforeEach(() => {
		cart.addItem(modifierLine({ delta: 0, note: "Regular", selection: { Size: ["Regular"] }, line_uid: "u-1" }), 1, false, null);
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-2" }), 1, false, null);
	});

	it("updateItemQuantity by line_uid changes only the addressed line", () => {
		cart.updateItemQuantity("ESPRESSO", 3, "Nos", "u-2");
		const large = cart.invoiceItems.find((l) => l.line_uid === "u-2");
		const regular = cart.invoiceItems.find((l) => l.line_uid === "u-1");
		expect(large.quantity).toBe(3);
		expect(regular.quantity).toBe(1);
		expect(cart.subtotal).toBe(55); // 10×1 + 15×3
	});

	it("removeItem by line_uid removes only the addressed line", () => {
		cart.removeItem("ESPRESSO", "Nos", "u-1");
		expect(cart.invoiceItems).toHaveLength(1);
		expect(cart.invoiceItems[0].line_uid).toBe("u-2");
		expect(cart.subtotal).toBe(15);
	});
});

describe("send-to-kitchen selection + marking on the live cart (utils/kot)", () => {
	it("fires only unsent lines, marks them sent, and re-firing is a no-op", () => {
		cart.addItem(modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1" }), 1, false, null);
		cart.addItem(modifierLine({ base: 12, delta: 2.5, note: "Oat Milk", selection: { Milk: ["Oat"] }, line_uid: "u-2" }), 1, false, null);

		const payload = selectUnsentKotItems(cart.invoiceItems);
		expect(payload.map((p) => p.item_code)).toEqual(["ESPRESSO", "ESPRESSO"]);
		expect(payload[1].notes).toBe("Oat Milk");

		// handleSendKitchen marks the just-fired lines sent by reassigning the cart.
		cart.invoiceItems = markCartLinesSent(cart.invoiceItems, "KOT-0001");
		expect(cart.invoiceItems.every((l) => l.sent_to_kitchen === 1)).toBe(true);
		expect(cart.invoiceItems.every((l) => l.kot === "KOT-0001")).toBe(true);
		expect(selectUnsentKotItems(cart.invoiceItems)).toEqual([]);
	});
});

describe("draft round-trip WITH table (posCart lines -> posDrafts)", () => {
	beforeEach(() => {
		_drafts.length = 0;
		_seq = 0;
	});

	it("preserves modifier fields + table across save -> findDraftByTable -> load", async () => {
		cart.addItem(
			modifierLine({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1" }),
			1,
			false,
			null
		);
		const drafts = usePOSDraftsStore();
		const saved = await drafts.saveDraftInvoice(
			cart.invoiceItems,
			"Walk-In",
			"Main POS",
			[],
			null,
			"TABLE-9"
		);
		expect(saved.table).toBe("TABLE-9");

		const found = await drafts.findDraftByTable("TABLE-9");
		expect(found.draft_id).toBe(saved.draft_id);
		const loaded = await drafts.loadDraft(found);
		const line = loaded.items[0];
		expect(line.modifier_note).toBe("Large");
		expect(line.modifier_selection).toEqual({ Size: ["Large"] });
		expect(line.line_uid).toBe("u-1");
		expect(line.price_list_rate).toBe(15);
		expect(loaded.table).toBe("TABLE-9");
	});
});

describe("retail no-op regression through the same wired path", () => {
	it("merges same item+uom, addresses by item_code+uom, and carries no modifier fields", () => {
		cart.addItem(retailLine(), 1, false, null);
		cart.addItem(retailLine(), 2, false, null);
		expect(cart.invoiceItems).toHaveLength(1);
		const line = cart.invoiceItems[0];
		expect(line.quantity).toBe(3);
		expect(line.line_uid).toBeUndefined();
		expect(line.modifier_note).toBeUndefined();
		expect(cart.subtotal).toBe(6); // 2 × 3

		// qty/remove without a line_uid behave exactly as before.
		cart.updateItemQuantity("WATER", 5, "Nos");
		expect(cart.invoiceItems[0].quantity).toBe(5);
		cart.removeItem("WATER", "Nos");
		expect(cart.invoiceItems).toHaveLength(0);
	});

	it("clearing the cart frees the active table (Q3 wiring)", () => {
		const restaurant = usePOSRestaurantStore();
		restaurant.setActiveTable("TABLE-3");
		cart.addItem(retailLine(), 1, false, null);
		cart.clearCart();
		expect(cart.invoiceItems).toHaveLength(0);
		expect(restaurant.activeTable == null).toBe(true);
	});
});
