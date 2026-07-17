import { defineStore } from "pinia";
import { ref } from "vue";
import { call } from "@/utils/apiWrapper";
import { usePOSCartStore } from "@/stores/posCart";
import { usePOSDraftsStore } from "@/stores/posDrafts";
import { usePOSShiftStore } from "@/stores/posShift";
import { markCartLinesSent, selectUnsentKotItems, unsentLineUids } from "@/utils/kot";

/**
 * Restaurant table-context store (Q3 LOCKED: POS Table Session is a presence
 * marker only, the live order stays in the per-device draft). This store owns the
 * table-context state AND the dine-in open/switch/KOT orchestration (spec: "holds
 * activeTable … and the open/switch orchestration so posCart.js stays clean"), so
 * the POSSale.vue handlers stay thin wrappers over these actions and the
 * orchestration is unit-testable end-to-end (driven directly, like posCart).
 *
 * `activeTable` is the table the main sell screen is currently bound to (null for a
 * plain retail sale / no table). `activeSession` is that table's Open POS Table
 * Session name — the cross-device presence marker; null when no session is held.
 */

// Unique per-cart-line id so two differently-modified instances of the same
// item+uom stay distinct lines (Q1 LOCKED: line_uid).
function makeLineUid() {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID();
	}
	return `L${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const usePOSRestaurantStore = defineStore("posRestaurant", () => {
	// null => retail / no table bound
	const activeTable = ref(null);
	// null => no cross-device presence session held for the active table
	const activeSession = ref(null);

	// item_code -> modifier groups. Lives in the store (not the SFC) so it survives
	// POSSale remounts (translation-version changes etc.) — an SFC-local ref reset to
	// {} on remount silently broke the picker after the first table (F1). Pinia
	// singletons persist across remounts, like activeTable/activeSession.
	const modifierGroupsMap = ref({});

	/**
	 * Load the item_code -> modifier-groups map once so the sell screen can decide
	 * synchronously whether an item needs the picker. Best-effort: on failure the map
	 * stays empty and every item behaves like a plain (no-modifier) item. Skips the
	 * server call if already populated unless force=true.
	 */
	async function loadModifierGroupsMap({ force = false } = {}) {
		if (!force && Object.keys(modifierGroupsMap.value).length) return modifierGroupsMap.value;
		try {
			const map = await call("pos_next.api.restaurant.get_item_modifiers");
			modifierGroupsMap.value = map && typeof map === "object" ? map : {};
		} catch (error) {
			modifierGroupsMap.value = {};
		}
		return modifierGroupsMap.value;
	}

	/** Modifier groups configured for one item ([] when none / not loaded). */
	function modifierGroupsFor(itemCode) {
		const g = modifierGroupsMap.value?.[itemCode];
		return Array.isArray(g) ? g : [];
	}

	function setActiveTable(table) {
		activeTable.value = table || null;
	}

	function clearActiveTable() {
		activeTable.value = null;
		// The presence pointer is local; the backend session (if any) is settled /
		// cancelled explicitly by settleSession/cancelSession on checkout/clear.
		activeSession.value = null;
	}

	function setActiveSession(name) {
		activeSession.value = name || null;
	}

	/**
	 * Q3 presence marker: create/touch the table's Open POS Table Session so floor
	 * occupancy (get_tables) is shared across devices. Best-effort — a presence
	 * failure must never block binding the table or loading its order. Caller passes
	 * `online` (Q5: the session is a server call; plain dine-in ordering still works
	 * offline, just without cross-device presence).
	 */
	async function touchSession(table, online = true) {
		if (!table || !online) {
			activeSession.value = null;
			return null;
		}
		const shift = usePOSShiftStore();
		try {
			const sess = await call("pos_next.api.restaurant.get_session", {
				table,
				create: 1,
				pos_profile: shift.profileName || null,
			});
			activeSession.value = sess?.name || null;
		} catch (error) {
			activeSession.value = null;
		}
		return activeSession.value;
	}

	/**
	 * Settle the active table's presence session against a submitted invoice
	 * (checkout). With no invoice name it falls back to cancelling. Best-effort: the
	 * bill already succeeded, so a stale Open session is only a soft floor-state issue.
	 */
	async function settleSession(salesInvoice) {
		const s = activeSession.value;
		if (!s) return;
		try {
			if (salesInvoice) {
				await call("pos_next.api.restaurant.session_settle", {
					session: s,
					sales_invoice: salesInvoice,
				});
			} else {
				await call("pos_next.api.restaurant.session_cancel", { session: s });
			}
		} catch (error) {
			// swallow — floor state can be reconciled later; never break checkout
		} finally {
			activeSession.value = null;
		}
	}

	/** Cancel (void) the active table's presence session — explicit cart clear. */
	async function cancelSession() {
		const s = activeSession.value;
		if (!s) return;
		try {
			await call("pos_next.api.restaurant.session_cancel", { session: s });
		} catch (error) {
			// best-effort
		} finally {
			activeSession.value = null;
		}
	}

	/**
	 * Bind the main cart to a table (open / switch). Mirrors handleLoadDraft's
	 * save-then-load so switching tables never loses the current order: save the
	 * current cart to its own table first (ABORT on failure — data-loss guard), then
	 * load the target table's draft or start an empty cart bound to it. The live order
	 * IS the draft (Q3/Q4 LOCKED). Offer reapplication + cart-hash bookkeeping stay in
	 * the POSSale wrapper (they are SFC watcher concerns); this returns the loaded
	 * draft (or null) so the wrapper can finish those steps.
	 *
	 * @returns {{ok:false, reason:string} | {ok:true, loaded:object|null}}
	 */
	async function openTable(table, { online = true } = {}) {
		if (!table) return { ok: false, reason: "no-table" };
		// Already on this table — nothing to switch.
		if (activeTable.value === table) return { ok: false, reason: "same-table" };

		const cart = usePOSCartStore();
		const drafts = usePOSDraftsStore();

		// Save the current cart to its own table before switching (data-loss guard).
		if (!cart.isEmpty) {
			const saved = await drafts.saveDraftInvoice(
				cart.invoiceItems,
				cart.customer,
				cart.posProfile,
				cart.appliedOffers,
				cart.currentDraftId,
				activeTable.value
			);
			if (!saved) return { ok: false, reason: "save-failed" };
		}

		let loaded = null;
		const existing = await drafts.findDraftByTable(table);
		if (existing) {
			const draftData = await drafts.loadDraft(existing);
			cart.invoiceItems = draftData.items;
			cart.setCustomer(draftData.customer);
			cart.currentDraftId = existing.draft_id;
			cart.appliedOffers = draftData.applied_offers || [];
			cart.rebuildIncrementalCache();
			loaded = draftData;
		} else {
			// No order yet for this table — start empty. clearCart() also resets the
			// previous table binding, so set the new one after it.
			cart.clearCart();
		}
		setActiveTable(table);
		await touchSession(table, online);
		return { ok: true, loaded };
	}

	/**
	 * A modifier selection was confirmed in ModifierDialog. Fetch the
	 * server-authoritative delta + note (Q2 LOCKED: delta-only), fold the delta onto
	 * the cart's own base rate, and add the line with a fresh line_uid + modifier
	 * fields. Throws to the caller on a pricing failure (nothing is added).
	 */
	async function confirmModifier(item, selection) {
		const cart = usePOSCartStore();
		const shift = usePOSShiftStore();
		const res = await call("pos_next.api.restaurant.get_modifier_selection", {
			item_code: item.item_code,
			modifiers: JSON.stringify(selection || {}),
		});
		const delta = Number(res?.delta) || 0;
		const note = res?.note || "";
		// Base is the cart's own price (pricing rules / customer price list / UOM).
		// The server modifier delta is added on top — one source of truth for base.
		const base = Number(item.price_list_rate ?? item.rate ?? 0);
		const rate = base + delta;
		cart.addItem(
			{
				...item,
				rate,
				price_list_rate: rate,
				modifier_note: note,
				modifier_selection: selection,
				line_uid: makeLineUid(),
				sent_to_kitchen: 0,
			},
			1,
			false,
			shift.currentProfile
		);
		return { ok: true, rate, note };
	}

	/**
	 * Fire the cart's unsent lines to the kitchen as a KOT, mark them sent so they are
	 * never silently re-fired, and persist the draft so the "sent" flag survives a
	 * table switch / reload. Requires a bound table: a KOT is routed by table and the
	 * sent-markers are persisted onto the table's draft, so with no table there is
	 * nowhere to persist them and a reload could re-fire the ticket (Reviewer item 5).
	 *
	 * @returns {{ok:false, reason:string} | {ok:true, kot:string}}
	 */
	async function sendKitchen() {
		const cart = usePOSCartStore();
		const drafts = usePOSDraftsStore();
		const shift = usePOSShiftStore();
		const table = activeTable.value;
		if (!table) return { ok: false, reason: "no-table" };

		// Stamp any unsent line missing a uid so the fired set is precisely
		// identified, then capture exactly which uids this KOT covers — a line added
		// while kot_send is in flight keeps a uid outside this set and stays unsent (F3).
		cart.invoiceItems.forEach((line) => {
			if (!line.sent_to_kitchen && !line.line_uid) line.line_uid = makeLineUid();
		});
		const items = selectUnsentKotItems(cart.invoiceItems);
		if (!items.length) return { ok: false, reason: "nothing-new" };
		const sentUids = unsentLineUids(cart.invoiceItems);

		// KOT customer_name is a display label; a Customer object exposes it as
		// customer_name (its .name is the id). A plain-string customer has no
		// resolvable label here, so send null rather than leaking the id (F4).
		const cust = cart.customer;
		const customerName =
			cust && typeof cust === "object" ? cust.customer_name || cust.name || null : null;

		const res = await call("pos_next.api.restaurant.kot_send", {
			table_label: table,
			items,
			pos_profile: shift.profileName || null,
			customer_name: customerName,
			table,
			session: activeSession.value || null,
		});
		const kot = res?.kot || res?.name || res?.message?.kot || res?.message?.name || "KOT";
		// Flip only the just-fired lines to sent and stamp the KOT (utils/kot).
		cart.invoiceItems = markCartLinesSent(cart.invoiceItems, kot, sentUids);
		// Persist so the sent marker survives a table switch / reload. A table is
		// always bound here (guarded above), so the draft is always table-tagged.
		const saved = await drafts.saveDraftInvoice(
			cart.invoiceItems,
			cart.customer,
			cart.posProfile,
			cart.appliedOffers,
			cart.currentDraftId,
			table
		);
		if (saved) cart.currentDraftId = saved.draft_id;
		return { ok: true, kot };
	}

	return {
		// State
		activeTable,
		activeSession,
		modifierGroupsMap,

		// State actions
		setActiveTable,
		clearActiveTable,
		setActiveSession,

		// Modifier map (hoisted so it survives POSSale remounts — F1)
		loadModifierGroupsMap,
		modifierGroupsFor,

		// Presence session (Q3)
		touchSession,
		settleSession,
		cancelSession,

		// Dine-in orchestration
		openTable,
		confirmModifier,
		sendKitchen,
	};
});
