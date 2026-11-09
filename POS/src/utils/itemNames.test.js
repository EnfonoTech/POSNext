import { describe, expect, it } from "vitest";
import { itemNames } from "./itemNames";

describe("itemNames", () => {
	const item = { item_name: "Arabic Coffee 250g", custom_item_name_arabic: "قهوة عربية 250 غ" };

	it("shows English first with the Arabic line under it in an LTR UI", () => {
		expect(itemNames(item, false)).toEqual({ primary: "Arabic Coffee 250g", secondary: "قهوة عربية 250 غ" });
	});

	it("shows Arabic first in an Arabic UI", () => {
		expect(itemNames(item, true)).toEqual({ primary: "قهوة عربية 250 غ", secondary: "Arabic Coffee 250g" });
	});

	it("keeps the upstream single line without an Arabic name", () => {
		expect(itemNames({ item_name: "LED Bulb 9W" }, true)).toEqual({ primary: "LED Bulb 9W", secondary: "" });
		expect(itemNames({ item_name: "X", custom_item_name_arabic: "  " }, false)).toEqual({ primary: "X", secondary: "" });
	});

	it("never repeats the same text twice", () => {
		expect(itemNames({ item_name: "Tea", custom_item_name_arabic: "Tea" }, false)).toEqual({ primary: "Tea", secondary: "" });
	});

	it("falls back to the Arabic name when there is no English one", () => {
		expect(itemNames({ custom_item_name_arabic: "ماء" }, false)).toEqual({ primary: "ماء", secondary: "" });
	});
});
