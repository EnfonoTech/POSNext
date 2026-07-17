// TDD (pre-implementation) — Dine-in on the main cart.
// Spec: .pipeline/spec.md  Test Plan "Money-math for modifier lines" + Edge Case
//        "Modifier line rate + note integrity through offers/tax".
//
// A modifier line is priced base+delta, so it must behave like any catalog line
// priced at base+delta: subtotal, item discount, offer discount and tax (inclusive
// AND exclusive) all compute on the modified price, and computeBackendRate (exposed
// via formatItemsForSubmission.rate) returns the modifier-inclusive rate in both
// tax modes. Hand-computed values use System-default currency precision 2 +
// Banker's rounding; the chosen numbers avoid any half-cent rounding ambiguity.
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED. The money-math on price_list_rate is
// already correct, but each test also asserts the line was built through the
// modifier add path (carries modifier_note / line_uid), which addItem does not do
// yet — so the suite is red until the additive line fields land.

import { beforeEach, describe, expect, it, vi } from "vitest";

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
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn(), reserveSerials: vi.fn() }),
}));

import { useInvoice } from "@/composables/useInvoice";

// base 10 + delta 5 => line rate 15
function largeEspresso(line_uid = "u-1") {
	return {
		item_code: "ESPRESSO",
		item_name: "Espresso",
		uom: "Nos",
		stock_uom: "Nos",
		rate: 15,
		price_list_rate: 15,
		conversion_factor: 1,
		modifier_note: "Large",
		modifier_selection: { Size: ["Large"] },
		line_uid,
		sent_to_kitchen: 0,
	};
}

function withTax(inv, { inclusive }) {
	inv.taxRules.value = [{ charge_type: "On Net Total", rate: 15 }];
	inv.setTaxInclusive(inclusive);
}

describe("modifier line money-math — tax exclusive", () => {
	let inv;
	beforeEach(() => {
		inv = useInvoice();
	});

	it("subtotal reflects (base+delta) × qty", () => {
		withTax(inv, { inclusive: false });
		inv.addItem(largeEspresso(), 2);
		// modifier field carried (RED until implemented) + math on 15 × 2
		expect(inv.invoiceItems.value[0].modifier_note).toBe("Large");
		expect(inv.subtotal.value).toBe(30);
	});

	it("net amount + tax computed on base+delta (no discount): net 30, tax 4.5", () => {
		withTax(inv, { inclusive: false });
		inv.addItem(largeEspresso(), 2);
		const line = inv.invoiceItems.value[0];
		expect(line.line_uid).toBe("u-1"); // RED guard: built via modifier add path
		expect(line.amount).toBe(30); // net
		expect(line.tax_amount).toBe(4.5); // 30 × 15%
	});

	it("item discount 10% applies to the modified price: net 27, tax 4.05", () => {
		withTax(inv, { inclusive: false });
		inv.addItem(largeEspresso(), 2);
		const line = inv.invoiceItems.value[0];
		line.discount_percentage = 10;
		inv.recalculateItem(line);
		expect(line.discount_amount).toBe(3); // 10% of 30
		expect(line.amount).toBe(27);
		expect(line.tax_amount).toBe(4.05);
	});

	it("offer discount (fixed amount) applies to the modified price: disc 6, net 24, tax 3.6", () => {
		withTax(inv, { inclusive: false });
		inv.addItem(largeEspresso(), 2);
		const line = inv.invoiceItems.value[0];
		line.discount_percentage = 0;
		line.discount_amount = 6;
		inv.recalculateItem(line);
		expect(line.amount).toBe(24);
		expect(line.tax_amount).toBe(3.6);
	});

	it("computeBackendRate (via formatItemsForSubmission) is the modifier-inclusive NET rate", () => {
		withTax(inv, { inclusive: false });
		inv.addItem(largeEspresso(), 2);
		const [row] = inv.formatItemsForSubmission(inv.invoiceItems.value);
		expect(row.rate).toBe(15); // net rate = amount(30)/qty(2)
		expect(row.price_list_rate).toBe(15);
	});
});

describe("modifier line money-math — tax inclusive", () => {
	let inv;
	beforeEach(() => {
		inv = useInvoice();
	});

	it("extracts net + tax from the gross base+delta line (no discount): net 26.09, tax 3.91", () => {
		withTax(inv, { inclusive: true });
		inv.addItem(largeEspresso(), 2);
		const line = inv.invoiceItems.value[0];
		expect(line.modifier_note).toBe("Large"); // RED guard
		expect(line.amount).toBe(26.09); // 30 / 1.15
		expect(line.tax_amount).toBe(3.91); // 30 - 26.09
	});

	it("with 10% discount: gross 27 → net 23.48, tax 3.52", () => {
		withTax(inv, { inclusive: true });
		inv.addItem(largeEspresso(), 2);
		const line = inv.invoiceItems.value[0];
		line.discount_percentage = 10;
		inv.recalculateItem(line);
		expect(line.discount_amount).toBe(3);
		expect(line.amount).toBe(23.48);
		expect(line.tax_amount).toBe(3.52);
	});

	it("computeBackendRate (via formatItemsForSubmission) is the modifier-inclusive GROSS rate", () => {
		withTax(inv, { inclusive: true });
		inv.addItem(largeEspresso(), 2);
		const line = inv.invoiceItems.value[0];
		line.discount_percentage = 10;
		inv.recalculateItem(line);
		const [row] = inv.formatItemsForSubmission([line]);
		// gross rate = price_list_rate(15) - discount(3)/qty(2) = 13.5
		expect(row.rate).toBe(13.5);
		expect(row.price_list_rate).toBe(15);
	});
});
