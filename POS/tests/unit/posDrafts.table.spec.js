// TDD (pre-implementation) — Dine-in on the main cart.
// Spec: .pipeline/spec.md  §"posDrafts.js" + Q4 (LOCKED: no migration, persist a
//        `table` field on the draft, filter/select in memory) + Test Plan
//        "Draft round-trip" and "Table switch".
//
// Subject: usePOSDraftsStore (POS/src/stores/posDrafts.js):
//   - saveDraftInvoice(items, customer, posProfile, appliedOffers, draftId, TABLE)
//     gains an optional trailing `table` arg persisted onto the draft record.
//   - new findDraftByTable(table) returns the NEWEST draft for a table.
//   - loadDraft round-trips modifier fields + table verbatim.
//   - A→B→A table switch restores each table's exact lines / customer / offers.
//
// draftManager is mocked with an in-memory store so the round-trip is faithful
// without IndexedDB (Q4 forbids a DB_VERSION bump; the `table` field must ride the
// existing `...sanitizedInvoiceData` spread, i.e. just be part of draftData).
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED. saveDraftInvoice ignores a 6th arg and
// never writes `table`; findDraftByTable does not exist.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/composables/useToast", () => ({
	useToast: () => ({
		showSuccess: vi.fn(),
		showError: vi.fn(),
		showWarning: vi.fn(),
	}),
}));

// In-memory draftManager mock mirroring the real contract: saveDraft assigns a
// draft_id + created_at and stores everything in draftData verbatim (incl. `table`);
// getAllDrafts returns newest-first; updateDraft merges onto the existing record.
const _store = [];
let _seq = 0;
vi.mock("@/utils/draftManager", () => ({
	saveDraft: vi.fn(async (invoiceData) => {
		_seq += 1;
		const draft = {
			id: _seq,
			draft_id: `DRAFT-${_seq}`,
			...JSON.parse(JSON.stringify(invoiceData || {})),
			created_at: new Date(Date.UTC(2026, 0, 1, 0, 0, _seq)).toISOString(),
			updated_at: new Date(Date.UTC(2026, 0, 1, 0, 0, _seq)).toISOString(),
		};
		_store.push(draft);
		return draft;
	}),
	updateDraft: vi.fn(async (draftId, invoiceData) => {
		const existing = _store.find((d) => d.draft_id === draftId);
		if (!existing) throw new Error("Draft not found");
		Object.assign(existing, JSON.parse(JSON.stringify(invoiceData || {})), {
			updated_at: new Date().toISOString(),
		});
		return existing;
	}),
	getAllDrafts: vi.fn(async () =>
		[..._store].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
	),
	getDraftsCount: vi.fn(async () => _store.length),
	deleteDraft: vi.fn(async (draftId) => {
		const i = _store.findIndex((d) => d.draft_id === draftId);
		if (i >= 0) _store.splice(i, 1);
		return true;
	}),
}));

import { usePOSDraftsStore } from "@/stores/posDrafts";

const PROFILE = "Main POS";
function modifierItems() {
	return [
		{
			item_code: "ESPRESSO",
			item_name: "Espresso",
			uom: "Nos",
			quantity: 1,
			rate: 15,
			price_list_rate: 15,
			modifier_note: "Large · Extra Shot",
			modifier_selection: { Size: ["Large"], Extras: ["Extra Shot"] },
			line_uid: "u-1",
			sent_to_kitchen: 1,
			kot: "KOT-0001",
		},
	];
}

beforeEach(() => {
	_store.length = 0;
	_seq = 0;
	setActivePinia(createPinia());
});

describe("posDrafts.saveDraftInvoice — table tagging (Q4)", () => {
	it("persists the `table` arg onto the saved draft", async () => {
		const store = usePOSDraftsStore();
		const saved = await store.saveDraftInvoice(
			modifierItems(),
			"Walk-In",
			PROFILE,
			[],
			null,
			"TABLE-7"
		);
		expect(saved).toBeTruthy();
		expect(saved.table).toBe("TABLE-7");
	});

	it("still refuses to save an empty cart (returns null) — switch relies on this guard", async () => {
		const store = usePOSDraftsStore();
		const saved = await store.saveDraftInvoice([], "Walk-In", PROFILE, [], null, "TABLE-7");
		expect(saved).toBeNull();
	});
});

describe("posDrafts.findDraftByTable", () => {
	it("returns the NEWEST draft bound to a given table", async () => {
		const store = usePOSDraftsStore();
		const older = await store.saveDraftInvoice(modifierItems(), "A", PROFILE, [], null, "TABLE-1");
		const newer = await store.saveDraftInvoice(modifierItems(), "B", PROFILE, [], null, "TABLE-1");
		await store.saveDraftInvoice(modifierItems(), "C", PROFILE, [], null, "TABLE-2");

		const found = await store.findDraftByTable("TABLE-1");
		expect(found).toBeTruthy();
		expect(found.draft_id).toBe(newer.draft_id);
		expect(found.draft_id).not.toBe(older.draft_id);
	});

	it("returns null/undefined for a table with no draft", async () => {
		const store = usePOSDraftsStore();
		await store.saveDraftInvoice(modifierItems(), "A", PROFILE, [], null, "TABLE-1");
		const found = await store.findDraftByTable("TABLE-99");
		expect(found == null).toBe(true);
	});
});

describe("posDrafts round-trip — modifier fields + table survive save→load", () => {
	it("loadDraft returns modifier_note / modifier_selection / line_uid / sent_to_kitchen / kot / table verbatim", async () => {
		const store = usePOSDraftsStore();
		const saved = await store.saveDraftInvoice(
			modifierItems(),
			"Walk-In",
			PROFILE,
			[{ offer: "HAPPY-HOUR" }],
			null,
			"TABLE-7"
		);
		const found = await store.findDraftByTable("TABLE-7");
		expect(found.draft_id).toBe(saved.draft_id);

		const loaded = await store.loadDraft(found);
		const line = loaded.items[0];
		expect(line.modifier_note).toBe("Large · Extra Shot");
		expect(line.modifier_selection).toEqual({ Size: ["Large"], Extras: ["Extra Shot"] });
		expect(line.line_uid).toBe("u-1");
		expect(line.sent_to_kitchen).toBe(1);
		expect(line.kot).toBe("KOT-0001");
		expect(loaded.customer).toBe("Walk-In");
		expect(loaded.applied_offers).toEqual([{ offer: "HAPPY-HOUR" }]);
		expect(found.table).toBe("TABLE-7");
	});
});

describe("posDrafts — table switch A → B → A restores each table's order", () => {
	it("restores exact lines / customer / offers for each table via findDraftByTable + loadDraft", async () => {
		const store = usePOSDraftsStore();

		const itemsA = [{ item_code: "ESPRESSO", uom: "Nos", quantity: 2, rate: 15, price_list_rate: 15, line_uid: "a1" }];
		const itemsB = [{ item_code: "LATTE", uom: "Nos", quantity: 1, rate: 12, price_list_rate: 12, line_uid: "b1" }];

		// open A, build order, (switch) save A
		const draftA = await store.saveDraftInvoice(itemsA, "Cust-A", PROFILE, [{ offer: "A-OFF" }], null, "TABLE-A");
		// switch to B: save B
		const draftB = await store.saveDraftInvoice(itemsB, "Cust-B", PROFILE, [{ offer: "B-OFF" }], null, "TABLE-B");

		// switch back to A
		const backToA = await store.findDraftByTable("TABLE-A");
		expect(backToA.draft_id).toBe(draftA.draft_id);
		const loadedA = await store.loadDraft(backToA);
		expect(loadedA.items.map((i) => i.item_code)).toEqual(["ESPRESSO"]);
		expect(loadedA.items[0].quantity).toBe(2);
		expect(loadedA.customer).toBe("Cust-A");
		expect(loadedA.applied_offers).toEqual([{ offer: "A-OFF" }]);

		// and B is still independently retrievable
		const backToB = await store.findDraftByTable("TABLE-B");
		expect(backToB.draft_id).toBe(draftB.draft_id);
		const loadedB = await store.loadDraft(backToB);
		expect(loadedB.items[0].item_code).toBe("LATTE");
		expect(loadedB.customer).toBe("Cust-B");
	});
});
