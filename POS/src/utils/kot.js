// Send-to-Kitchen selection/marking as pure list logic, so the POSSale.vue
// handler stays a thin wrapper (spec Step 5). A KOT fires only the cart lines that
// have NOT been sent yet; already-sent lines are locked (already cooking) and are
// never re-fired or mutated — a re-order of a sent item is a fresh unsent line
// upstream in useInvoice.addItem, so this only ever needs the sent_to_kitchen flag.

/**
 * Build the kot_send payload from the UNSENT cart lines only.
 * Folds the modifier_note into `notes` so the kitchen ticket carries the selection.
 * @param {Array} cartItems - cart lines
 * @returns {Array<{item_code, item_name, qty, notes}>}
 */
export function selectUnsentKotItems(cartItems) {
	const items = Array.isArray(cartItems) ? cartItems : [];
	return items
		.filter((line) => !line.sent_to_kitchen)
		.map((line) => ({
			item_code: line.item_code,
			item_name: line.item_name,
			qty: line.quantity ?? line.qty ?? 1,
			notes: line.modifier_note || "",
		}));
}

/** line_uids of the currently-unsent lines — the exact set a KOT will fire. */
export function unsentLineUids(cartItems) {
	const items = Array.isArray(cartItems) ? cartItems : [];
	return items.filter((line) => !line.sent_to_kitchen).map((line) => line.line_uid);
}

/**
 * Return a new cart array with the KOT'd lines flipped to sent_to_kitchen:1 and
 * stamped with the returned KOT. Already-sent lines are returned untouched.
 *
 * When `uids` is given, ONLY lines whose line_uid is in that set are marked — a
 * line added while kot_send was in flight (its uid not captured) stays unsent and
 * is not silently dropped from a later ticket (F3). When `uids` is null the old
 * behaviour applies (mark every unsent line) for back-compat.
 * @param {Array} cartItems - cart lines
 * @param {string} kot - the KOT ticket name returned by kot_send
 * @param {Array<string>|null} [uids] - line_uids that were actually fired
 * @returns {Array} new cart array
 */
export function markCartLinesSent(cartItems, kot, uids = null) {
	const items = Array.isArray(cartItems) ? cartItems : [];
	const set = uids ? new Set(uids) : null;
	return items.map((line) => {
		if (line.sent_to_kitchen) return line;
		if (set && !set.has(line.line_uid)) return line; // added mid-flight — leave unsent
		return { ...line, sent_to_kitchen: 1, kot };
	});
}
