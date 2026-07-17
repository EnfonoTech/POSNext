// TDD (pre-implementation) — Dine-in on the main cart.
// Spec: .pipeline/spec.md  Implementation Step 5 "Send-to-Kitchen from the cart" +
//        Test Plan "Send-to-Kitchen selection" + Edge Case "A line already sent to
//        kitchen vs edited after".
//
// The Send-to-Kitchen handler in POSSale.vue builds the kot_send payload from the
// UNSENT cart lines only, then marks exactly those lines sent_to_kitchen:1 and
// stamps the returned KOT. That selection/marking is pure list logic and is
// specified here as a small, unit-testable utility so the handler stays a thin
// wrapper. Contract (module `@/utils/kot`):
//   selectUnsentKotItems(cartItems)  -> [{ item_code, item_name, qty, notes }]
//        only lines with a falsy sent_to_kitchen, notes := modifier_note (folds in).
//   markCartLinesSent(cartItems, kot) -> new array; previously-unsent lines flip to
//        sent_to_kitchen:1 with kot set; already-sent lines are untouched.
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED — `@/utils/kot` does not exist yet.

import { describe, expect, it } from "vitest";
import { markCartLinesSent, selectUnsentKotItems, unsentLineUids } from "@/utils/kot";

function cart() {
	return [
		{
			item_code: "ESPRESSO",
			item_name: "Espresso",
			quantity: 2,
			uom: "Nos",
			modifier_note: "Large · Extra Shot",
			line_uid: "u-1",
			sent_to_kitchen: 1,
			kot: "KOT-0001",
		},
		{
			item_code: "LATTE",
			item_name: "Latte",
			quantity: 1,
			uom: "Nos",
			modifier_note: "Oat Milk",
			line_uid: "u-2",
			sent_to_kitchen: 0,
		},
		{
			item_code: "WATER",
			item_name: "Water",
			quantity: 3,
			uom: "Nos",
			modifier_note: "",
			line_uid: "u-3",
			sent_to_kitchen: 0,
		},
	];
}

describe("selectUnsentKotItems", () => {
	it("includes only lines that have NOT been sent to kitchen", () => {
		const payload = selectUnsentKotItems(cart());
		const codes = payload.map((i) => i.item_code).sort();
		expect(codes).toEqual(["LATTE", "WATER"]);
		expect(payload.some((i) => i.item_code === "ESPRESSO")).toBe(false);
	});

	it("carries qty and folds the modifier_note into `notes`", () => {
		const payload = selectUnsentKotItems(cart());
		const latte = payload.find((i) => i.item_code === "LATTE");
		expect(latte.qty).toBe(1);
		expect(latte.notes).toBe("Oat Milk");
	});

	it("returns an empty payload when every line is already sent (no re-fire)", () => {
		const allSent = cart().map((l) => ({ ...l, sent_to_kitchen: 1, kot: "KOT-0001" }));
		expect(selectUnsentKotItems(allSent)).toEqual([]);
	});
});

describe("markCartLinesSent", () => {
	it("flips previously-unsent lines to sent_to_kitchen:1 and stamps the KOT", () => {
		const marked = markCartLinesSent(cart(), "KOT-0002");
		const latte = marked.find((i) => i.line_uid === "u-2");
		const water = marked.find((i) => i.line_uid === "u-3");
		expect(latte.sent_to_kitchen).toBe(1);
		expect(latte.kot).toBe("KOT-0002");
		expect(water.sent_to_kitchen).toBe(1);
		expect(water.kot).toBe("KOT-0002");
	});

	it("leaves already-sent lines untouched (keeps their original KOT)", () => {
		const marked = markCartLinesSent(cart(), "KOT-0002");
		const espresso = marked.find((i) => i.line_uid === "u-1");
		expect(espresso.sent_to_kitchen).toBe(1);
		expect(espresso.kot).toBe("KOT-0001");
	});

	it("re-tapping Send with nothing new selects an empty payload (no-op)", () => {
		const marked = markCartLinesSent(cart(), "KOT-0002");
		expect(selectUnsentKotItems(marked)).toEqual([]);
	});
});

describe("markCartLinesSent with a captured uid set (F3 — mid-flight add stays unsent)", () => {
	it("unsentLineUids returns the uids of the currently-unsent lines", () => {
		expect(unsentLineUids(cart()).sort()).toEqual(["u-2", "u-3"]);
	});

	it("marks only the captured uids; a line added during kot_send stays unsent", () => {
		// Capture the unsent set (u-2, u-3), then a new line arrives mid-flight.
		const sentUids = unsentLineUids(cart());
		const withNew = [
			...cart(),
			{ item_code: "COOKIE", item_name: "Cookie", quantity: 1, uom: "Nos", line_uid: "u-4", sent_to_kitchen: 0 },
		];
		const marked = markCartLinesSent(withNew, "KOT-0002", sentUids);
		expect(marked.find((l) => l.line_uid === "u-2").sent_to_kitchen).toBe(1);
		expect(marked.find((l) => l.line_uid === "u-3").sent_to_kitchen).toBe(1);
		// The mid-flight line was NOT in the fired set → still unsent, not dropped.
		const cookie = marked.find((l) => l.line_uid === "u-4");
		expect(cookie.sent_to_kitchen).toBe(0);
		expect(cookie.kot).toBeUndefined();
		// And it is picked up by the next Send.
		expect(selectUnsentKotItems(marked).map((i) => i.item_code)).toEqual(["COOKIE"]);
	});
});
