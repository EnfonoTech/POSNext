/**
 * Bilingual item-name helpers (Feature 3).
 *
 * `arabicLabel` is a pure no-op gate: it returns the trimmed Arabic name when a
 * truthy `custom_arabic_name` is present, and "" (falsy) otherwise, so the second
 * RTL line's `v-if` never renders for retail / un-named items. Defensive against a
 * null/undefined item and a whitespace-only value (treated as empty).
 *
 * @param {{custom_arabic_name?: string}|null|undefined} item
 * @returns {string} the trimmed Arabic name, or "" when absent/empty
 */
export function arabicLabel(item) {
	const ar = item && item.custom_arabic_name;
	if (typeof ar !== "string") return "";
	return ar.trim();
}
