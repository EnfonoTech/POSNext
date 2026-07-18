// TDD (pre-implementation) — Feature 3: Bilingual item names (frontend util).
//
// Spec: .pipeline/spec.md §"Files To Modify / Create → Feature 3":
//   NEW (optional) POS/src/utils/bilingual.js — arabicLabel(item) helper (unit-tested).
// And §"Test Plan → Frontend": "bilingual.spec.js — arabicLabel(item) returns ''
//   for missing/empty (drives the v-if no-op); returns the value when set."
// And §"Edge Cases → Feature 3": "Empty-field no-op: custom_arabic_name blank →
//   cards/cart/KOT render exactly as today ... no second UI line."
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED — @/utils/bilingual does not exist yet.
//
// The helper is a pure no-op gate: it returns the trimmed Arabic label when a
// truthy custom_arabic_name is present, and "" (falsy) otherwise, so the second
// RTL line's v-if never renders for retail / un-named items.

import { describe, expect, it } from "vitest";

import { arabicLabel } from "@/utils/bilingual";

describe("arabicLabel — bilingual item-name gate (Feature 3)", () => {
	it("returns the Arabic name when set", () => {
		expect(arabicLabel({ custom_arabic_name: "لاتيه" })).toBe("لاتيه");
	});

	it("returns '' for an empty custom_arabic_name (no-op)", () => {
		expect(arabicLabel({ custom_arabic_name: "" })).toBe("");
	});

	it("returns '' when custom_arabic_name is missing (no-op)", () => {
		expect(arabicLabel({ item_code: "LATTE", item_name: "Latte" })).toBe("");
	});

	it("returns '' for null / undefined item (defensive no-op)", () => {
		expect(arabicLabel(null)).toBe("");
		expect(arabicLabel(undefined)).toBe("");
	});

	it("returns '' for a whitespace-only Arabic name (treated as empty)", () => {
		expect(arabicLabel({ custom_arabic_name: "   " })).toBe("");
	});

	it("trims surrounding whitespace on a real value", () => {
		expect(arabicLabel({ custom_arabic_name: "  لاتيه  " })).toBe("لاتيه");
	});
});
