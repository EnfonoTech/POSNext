/**
 * Enfono: which name a POS item shows first, and the second line under it.
 *
 * Arabic names live in Item.custom_item_name_arabic (fateh_erp_v2 ships the field; the print
 * formats read the same one). Without an Arabic name the card shows item_name alone, as upstream.
 *
 * @param {{item_name?: string, custom_item_name_arabic?: string}} item
 * @param {boolean} rtl the UI is right-to-left (Arabic)
 * @returns {{primary: string, secondary: string}}
 */
export function itemNames(item, rtl) {
	const en = (item?.item_name || "").trim();
	const ar = (item?.custom_item_name_arabic || "").trim();
	if (!ar || ar === en) return { primary: en || ar, secondary: "" };
	if (!en) return { primary: ar, secondary: "" };
	return rtl ? { primary: ar, secondary: en } : { primary: en, secondary: ar };
}
