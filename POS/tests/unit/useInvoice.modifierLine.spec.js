// TDD (pre-implementation) — Dine-in on the main cart.
// Spec: .pipeline/spec.md  §"Functions … useInvoice.js"  + Q1 (LOCKED: line_uid),
//        Q2 (LOCKED: delta-only) + Test Plan "Merge behavior" / "line construction".
//
// Subject: useInvoice().addItem (POS/src/composables/useInvoice.js:218) and the
// new-line literal (lines ~259-291). These MUST become additive carriers of the
// restaurant modifier fields and MUST route merge by a modifier signature +
// line_uid so two differently-modified instances of the same item+uom are two
// lines, while retail (no modifier fields) merges byte-for-byte as today.
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED. Today addItem drops modifier_note /
// modifier_selection / line_uid / sent_to_kitchen / kot and merges purely on
// item_code+uom, so the modifier-line and split-line assertions fail. The retail
// regression block is a GREEN guardrail that must stay green after implementation.

import { beforeEach, describe, expect, it, vi } from "vitest";

// Isolate useInvoice from network / stores / offline cache.
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
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: () => null,
}));
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({
		returnSerials: vi.fn(),
		reserveSerials: vi.fn(),
		releaseSerials: vi.fn(),
	}),
}));

import { useInvoice } from "@/composables/useInvoice";

// A base menu item priced by the cart's own engine (base 10). The dine-in add
// flow adds the server modifier delta ON TOP (Q2 delta-only), so the caller hands
// addItem an item whose price_list_rate === rate === base + delta.
function modifierItem({ delta, note, selection, line_uid }) {
	const base = 10;
	const rate = base + delta;
	return {
		item_code: "ESPRESSO",
		item_name: "Espresso",
		uom: "Nos",
		stock_uom: "Nos",
		rate,
		price_list_rate: rate,
		conversion_factor: 1,
		// Restaurant modifier fields the add flow must thread through:
		modifier_note: note,
		modifier_selection: selection,
		line_uid,
		sent_to_kitchen: 0,
	};
}

function retailItem(overrides = {}) {
	return {
		item_code: "WATER",
		item_name: "Water Bottle",
		uom: "Nos",
		stock_uom: "Nos",
		rate: 2,
		price_list_rate: 2,
		conversion_factor: 1,
		...overrides,
	};
}

describe("useInvoice.addItem — modifier line construction (Q1 line_uid, Q2 delta-only)", () => {
	let inv;
	beforeEach(() => {
		inv = useInvoice();
		inv.taxRules.value = [];
		inv.setTaxInclusive(false);
	});

	it("carries every modifier field onto the new cart line", () => {
		const sel = { Size: ["Large"], Extras: ["Extra Shot"] };
		inv.addItem(
			modifierItem({ delta: 8, note: "Large · Extra Shot", selection: sel, line_uid: "u-1" }),
			1
		);
		const line = inv.invoiceItems.value[0];
		expect(line.modifier_note).toBe("Large · Extra Shot");
		expect(line.modifier_selection).toEqual(sel);
		expect(line.line_uid).toBe("u-1");
		expect(line.sent_to_kitchen).toBe(0);
	});

	it("sets price_list_rate === rate === base + delta on the modifier line", () => {
		inv.addItem(
			modifierItem({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-1" }),
			1
		);
		const line = inv.invoiceItems.value[0];
		expect(line.price_list_rate).toBe(15);
		expect(line.rate).toBe(15);
	});

	it("defaults sent_to_kitchen to 0 for a freshly added modifier line", () => {
		inv.addItem(
			modifierItem({ delta: 0, note: "Regular", selection: { Size: ["Regular"] }, line_uid: "u-1" }),
			1
		);
		expect(inv.invoiceItems.value[0].sent_to_kitchen).toBe(0);
	});
});

describe("useInvoice.addItem — merge behavior by modifier signature", () => {
	let inv;
	beforeEach(() => {
		inv = useInvoice();
		inv.taxRules.value = [];
		inv.setTaxInclusive(false);
	});

	it("merges (increments qty) when the same item has the SAME modifier selection", () => {
		const sel = { Size: ["Large"] };
		inv.addItem(modifierItem({ delta: 5, note: "Large", selection: sel, line_uid: "u-1" }), 1);
		// second add: fresh line_uid, but identical signature -> must MERGE into the existing line
		inv.addItem(modifierItem({ delta: 5, note: "Large", selection: sel, line_uid: "u-2" }), 1);

		expect(inv.invoiceItems.value).toHaveLength(1);
		expect(inv.invoiceItems.value[0].quantity).toBe(2);
		// merge keeps the ORIGINAL line's identity (merge is by signature, not the new uid)
		expect(inv.invoiceItems.value[0].line_uid).toBe("u-1");
	});

	it("creates TWO distinct lines when the same item has DIFFERENT modifier selections", () => {
		inv.addItem(
			modifierItem({ delta: 0, note: "Regular", selection: { Size: ["Regular"] }, line_uid: "u-1" }),
			1
		);
		inv.addItem(
			modifierItem({ delta: 5, note: "Large", selection: { Size: ["Large"] }, line_uid: "u-2" }),
			1
		);

		expect(inv.invoiceItems.value).toHaveLength(2);
		const notes = inv.invoiceItems.value.map((l) => l.modifier_note).sort();
		expect(notes).toEqual(["Large", "Regular"]);
		const rates = inv.invoiceItems.value.map((l) => l.price_list_rate).sort((a, b) => a - b);
		expect(rates).toEqual([10, 15]);
		const uids = inv.invoiceItems.value.map((l) => l.line_uid).sort();
		expect(uids).toEqual(["u-1", "u-2"]);
	});

	it("does NOT merge a re-order into a line already sent to kitchen — it becomes a new unsent line", () => {
		// Mirrors the server rule (_session_add_line, restaurant.py:238-243): sent lines
		// are locked; a re-order of a sent item is a fresh unsent line so KOT never re-fires.
		const sel = { Size: ["Large"] };
		inv.addItem(modifierItem({ delta: 5, note: "Large", selection: sel, line_uid: "u-1" }), 1);
		// mark the first line as already fired
		inv.invoiceItems.value[0].sent_to_kitchen = 1;
		inv.invoiceItems.value[0].kot = "KOT-0001";

		inv.addItem(modifierItem({ delta: 5, note: "Large", selection: sel, line_uid: "u-2" }), 1);

		expect(inv.invoiceItems.value).toHaveLength(2);
		const sent = inv.invoiceItems.value.find((l) => l.sent_to_kitchen === 1);
		const unsent = inv.invoiceItems.value.find((l) => !l.sent_to_kitchen);
		expect(sent.line_uid).toBe("u-1");
		expect(sent.kot).toBe("KOT-0001");
		expect(sent.quantity).toBe(1);
		expect(unsent.line_uid).toBe("u-2");
		expect(unsent.quantity).toBe(1);
	});
});

describe("useInvoice.addItem — retail no-op regression (GREEN guardrail)", () => {
	let inv;
	beforeEach(() => {
		inv = useInvoice();
		inv.taxRules.value = [];
		inv.setTaxInclusive(false);
	});

	it("merges same item+uom exactly as before when there are no modifier fields", () => {
		inv.addItem(retailItem(), 1);
		inv.addItem(retailItem(), 2);
		expect(inv.invoiceItems.value).toHaveLength(1);
		expect(inv.invoiceItems.value[0].quantity).toBe(3);
	});

	it("keeps distinct lines for the same item across different UOMs (unchanged)", () => {
		inv.addItem(retailItem({ uom: "Nos" }), 1);
		inv.addItem(retailItem({ uom: "Box", price_list_rate: 20, rate: 20 }), 1);
		expect(inv.invoiceItems.value).toHaveLength(2);
	});

	it("does not attach an empty/undefined modifier signature that would break retail merge", () => {
		inv.addItem(retailItem(), 1);
		const line = inv.invoiceItems.value[0];
		// a retail line must not carry a truthy modifier_note that would split future merges
		expect(line.modifier_note || "").toBe("");
	});
});
