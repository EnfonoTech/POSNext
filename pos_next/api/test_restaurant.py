# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

"""
TDD test suite for the POSNext Restaurant *menu-item modifier* feature and its
desk Workspace + seed patch.  Written BEFORE implementation — every test here
must currently FAIL (the symbols / DocTypes / fixtures / patch do not exist
yet) and must PASS once the spec in .pipeline/spec.md is implemented.

Covers (see spec "Test Plan"):
  - _resolve_item_modifiers  : ordered structure, disabled exclusion, empty item
  - _price_with_modifiers    : flt pricing math, single/multiple, required/min/max,
                               foreign option / unknown group, empty selection,
                               dict + JSON-string input, server-only trust boundary
  - get_item_modifiers       : single-item + full-map return, whitelisted-not-guest,
                               works for a plain authenticated cashier (perms bypassed)
  - session_add_item(...,modifiers=...) : additive no-modifier regression, rate =
                               base + deltas, note summary, distinct-selection ->
                               distinct line, identical -> qty merge, note -> KOT
  - Restaurant Workspace     : fixture present after migrate, module correct
  - seed_restaurant_modifiers: idempotent (run twice -> no dup groups/options/links),
                               attach is a production-safe no-op with no demo Item,
                               seeded groups price correctly through _price_with_modifiers

The module-level import of the not-yet-existing helpers is intentional: until the
API is implemented the import raises ImportError and the whole suite reports RED,
which is the correct pre-implementation TDD signal.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

# These three do NOT exist yet -> ImportError until implemented (correct RED state).
from pos_next.api.restaurant import (
	_price_with_modifiers,
	_resolve_item_modifiers,
	get_item_modifiers,
	get_session,
	session_add_item,
	session_send_kitchen,
)

# ── fixture identifiers ────────────────────────────────────────────────
TABLE = "T-MOD-TEST-1"
ITEM_MOD = "_Test Mod Item"        # base rate 10, has Size(req) + Extras + MinTwo + DisabledGroup
ITEM_PLAIN = "_Test Plain Item"    # base rate 10, no modifier groups
ITEM_OPT = "_Test OptOnly Item"    # base rate 8, only the optional Extras group
ITEM_DISABLED = "_Test Disabled Item"  # disabled=1 -> _resolve_rate must throw

G_SIZE = "_Test Size"              # Single, required
G_EXTRAS = "_Test Extras"          # Multiple, max_select 2, contains a disabled option
G_MINTWO = "_Test MinTwo"          # Multiple, min_select 2, max_select 0 (unlimited)
G_DISABLED = "_Test DisabledGroup"  # disabled group -> excluded from resolution


def _item_group():
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"


def _ensure_item(code, rate=10, disabled=0):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": _item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"standard_rate": rate,
				"disabled": disabled,
			}
		).insert(ignore_permissions=True)


def _ensure_group(name, selection_type, options, is_required=0, min_select=0, max_select=0, disabled=0):
	if frappe.db.exists("POS Modifier Group", name):
		return
	frappe.get_doc(
		{
			"doctype": "POS Modifier Group",
			"group_name": name,
			"selection_type": selection_type,
			"is_required": is_required,
			"min_select": min_select,
			"max_select": max_select,
			"disabled": disabled,
			"options": options,
		}
	).insert(ignore_permissions=True)


def _attach_groups(item_code, group_names):
	item = frappe.get_doc("Item", item_code)
	item.set("custom_modifier_groups", [])
	for g in group_names:
		item.append("custom_modifier_groups", {"modifier_group": g})
	item.save(ignore_permissions=True)


def _setup_modifier_fixtures():
	"""Idempotent: create the test items, modifier groups + options, and attach."""
	if not frappe.db.exists("POS Table", TABLE):
		frappe.get_doc(
			{"doctype": "POS Table", "table_name": TABLE, "seats": 4, "area": "Test"}
		).insert(ignore_permissions=True)

	_ensure_item(ITEM_MOD, rate=10)
	_ensure_item(ITEM_PLAIN, rate=10)
	_ensure_item(ITEM_OPT, rate=8)
	_ensure_item(ITEM_DISABLED, rate=10, disabled=1)

	_ensure_group(
		G_SIZE,
		"Single",
		is_required=1,
		options=[
			{"option_label": "Regular", "price_delta": 0, "is_default": 1},
			{"option_label": "Large", "price_delta": 5.00},
			{"option_label": "Small", "price_delta": 1.50},
		],
	)
	_ensure_group(
		G_EXTRAS,
		"Multiple",
		min_select=0,
		max_select=2,
		options=[
			{"option_label": "Extra Shot", "price_delta": 3.00},
			{"option_label": "Whipped Cream", "price_delta": 2.00},
			{"option_label": "Oat Milk", "price_delta": 2.50},
			{"option_label": "Truffle", "price_delta": 9.00, "disabled": 1},  # excluded
		],
	)
	_ensure_group(
		G_MINTWO,
		"Multiple",
		min_select=2,
		max_select=0,  # unlimited
		options=[
			{"option_label": "MA", "price_delta": 1.50},
			{"option_label": "MB", "price_delta": 0.25},
			{"option_label": "MC", "price_delta": 4.00},
		],
	)
	_ensure_group(
		G_DISABLED,
		"Single",
		disabled=1,
		options=[{"option_label": "DX", "price_delta": 4.00}],
	)

	_attach_groups(ITEM_MOD, [G_SIZE, G_EXTRAS, G_MINTWO, G_DISABLED])
	_attach_groups(ITEM_OPT, [G_EXTRAS])
	# ITEM_PLAIN deliberately has no groups


def _close_open_sessions():
	for name in frappe.get_all(
		"POS Table Session", filters={"table": TABLE, "status": "Open"}, pluck="name"
	):
		frappe.db.set_value("POS Table Session", name, "status", "Cancelled", update_modified=False)
	for name in frappe.get_all("KOT Ticket", filters={"status": "Open"}, pluck="name"):
		frappe.db.set_value("KOT Ticket", name, "status", "Cancelled", update_modified=False)


# ══════════════════════════════════════════════════════════════════════
#  _resolve_item_modifiers
# ══════════════════════════════════════════════════════════════════════
class TestResolveItemModifiers(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_setup_modifier_fixtures()

	def test_returns_ordered_config_structure(self):
		groups = _resolve_item_modifiers(ITEM_MOD)
		# disabled group is excluded; the rest keep config (idx) order
		names = [g["group_name"] for g in groups]
		self.assertEqual(names, [G_SIZE, G_EXTRAS, G_MINTWO])

	def test_group_shape_matches_contract(self):
		size = next(g for g in _resolve_item_modifiers(ITEM_MOD) if g["group_name"] == G_SIZE)
		for key in ("group_name", "selection_type", "is_required", "min", "max", "options"):
			self.assertIn(key, size)
		self.assertEqual(size["selection_type"], "Single")
		self.assertTrue(size["is_required"])
		opt = size["options"][0]
		for key in ("label", "price_delta", "is_default"):
			self.assertIn(key, opt)

	def test_disabled_group_excluded(self):
		names = [g["group_name"] for g in _resolve_item_modifiers(ITEM_MOD)]
		self.assertNotIn(G_DISABLED, names)

	def test_disabled_option_excluded(self):
		extras = next(g for g in _resolve_item_modifiers(ITEM_MOD) if g["group_name"] == G_EXTRAS)
		labels = [o["label"] for o in extras["options"]]
		self.assertNotIn("Truffle", labels)
		self.assertEqual(labels, ["Extra Shot", "Whipped Cream", "Oat Milk"])

	def test_item_without_groups_returns_empty(self):
		self.assertEqual(_resolve_item_modifiers(ITEM_PLAIN), [])

	def test_no_cross_item_cache_bleed(self):
		# per-request frappe.flags cache must key by item; different items -> different results
		a = _resolve_item_modifiers(ITEM_MOD)
		b = _resolve_item_modifiers(ITEM_PLAIN)
		self.assertTrue(a)
		self.assertEqual(b, [])
		# repeat call returns an equal structure (idempotent within request)
		self.assertEqual(
			[g["group_name"] for g in _resolve_item_modifiers(ITEM_MOD)],
			[g["group_name"] for g in a],
		)


# ══════════════════════════════════════════════════════════════════════
#  _price_with_modifiers
# ══════════════════════════════════════════════════════════════════════
class TestPriceWithModifiers(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_setup_modifier_fixtures()

	# ---- pricing math (flt) ----
	def test_single_plus_multiple_sums_deltas(self):
		rate, _sel, note = _price_with_modifiers(
			ITEM_MOD, 10, {G_SIZE: "Regular", G_EXTRAS: ["Extra Shot", "Oat Milk"]}
		)
		# 10 + 0 (Regular) + 3 (Extra Shot) + 2.5 (Oat Milk)
		self.assertEqual(flt(rate), 15.5)

	def test_currency_precision(self):
		rate, _sel, _note = _price_with_modifiers(
			ITEM_MOD, 10, {G_SIZE: "Small", G_MINTWO: ["MA", "MB"]}
		)
		# 10 + 1.50 (Small) + 1.50 (MA) + 0.25 (MB) = 13.25
		self.assertEqual(flt(rate), 13.25)

	def test_large_single_delta(self):
		rate, _sel, note = _price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Large"})
		self.assertEqual(flt(rate), 15.0)
		self.assertEqual(note, "Large")

	def test_accepts_json_string_selection(self):
		sel = json.dumps({G_SIZE: "Large", G_EXTRAS: ["Extra Shot"]})
		rate, _sel, note = _price_with_modifiers(ITEM_MOD, 10, sel)
		self.assertEqual(flt(rate), 18.0)  # 10 + 5 + 3
		# note follows config order across groups: Size before Extras
		self.assertEqual(note, "Large · Extra Shot")

	def test_note_joins_selected_labels_in_config_order(self):
		# pick Extras in reverse config order -> note still config-ordered
		_rate, _sel, note = _price_with_modifiers(
			ITEM_MOD, 10, {G_SIZE: "Regular", G_EXTRAS: ["Whipped Cream", "Extra Shot"]}
		)
		self.assertEqual(note, "Regular · Extra Shot · Whipped Cream")

	# ---- empty selection ----
	def test_empty_selection_no_required_returns_base(self):
		for empty in (None, {}, ""):
			rate, sel, note = _price_with_modifiers(ITEM_OPT, 8, empty)
			self.assertEqual(flt(rate), 8.0)
			self.assertEqual(note, "")
			self.assertFalse(sel)

	def test_optional_group_left_blank_is_valid(self):
		# ITEM_MOD has required Size; provide only Size, omit optional MinTwo/Extras
		rate, _sel, note = _price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Regular"})
		self.assertEqual(flt(rate), 10.0)
		self.assertEqual(note, "Regular")

	# ---- validation throws ----
	def test_required_but_empty_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_price_with_modifiers(ITEM_MOD, 10, {})  # Size required, none picked

	def test_single_with_two_picks_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: ["Regular", "Large"]})

	def test_below_min_select_throws(self):
		with self.assertRaises(frappe.ValidationError):
			# MinTwo engaged with only one pick (min_select=2)
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Regular", G_MINTWO: ["MA"]})

	def test_above_max_select_throws(self):
		with self.assertRaises(frappe.ValidationError):
			# Extras max_select=2, three picked
			_price_with_modifiers(
				ITEM_MOD, 10, {G_SIZE: "Regular", G_EXTRAS: ["Extra Shot", "Whipped Cream", "Oat Milk"]}
			)

	def test_max_select_zero_is_unlimited(self):
		rate, _sel, _note = _price_with_modifiers(
			ITEM_MOD, 10, {G_SIZE: "Regular", G_MINTWO: ["MA", "MB", "MC"]}
		)
		# 10 + 1.5 + 0.25 + 4.0 = 15.75 (MinTwo max_select=0 -> unlimited)
		self.assertEqual(flt(rate), 15.75)

	def test_unknown_group_for_item_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Regular", "No Such Group": "X"})

	def test_foreign_option_throws(self):
		with self.assertRaises(frappe.ValidationError):
			# "Large" belongs to Size, not Extras
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Regular", G_EXTRAS: ["Large"]})

	# ---- disabled handling ----
	def test_selecting_disabled_group_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Regular", G_DISABLED: "DX"})

	def test_selecting_disabled_option_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Regular", G_EXTRAS: ["Truffle"]})

	# ---- trust boundary: price is server-derived only ----
	def test_price_is_server_derived_only(self):
		# Client can only send labels; deltas come from server config regardless of
		# any price-like noise a caller might try to smuggle in the selection value.
		rate, _sel, _note = _price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "Large"})
		self.assertEqual(flt(rate), 15.0)  # exactly base(10) + server delta(5)
		# a fabricated numeric "price" as the selected label is just an unknown option
		with self.assertRaises(frappe.ValidationError):
			_price_with_modifiers(ITEM_MOD, 10, {G_SIZE: "999"})


# ══════════════════════════════════════════════════════════════════════
#  get_item_modifiers  (whitelisted read endpoint)
# ══════════════════════════════════════════════════════════════════════
class TestGetItemModifiers(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_setup_modifier_fixtures()

	def test_single_item_returns_resolved_groups(self):
		groups = get_item_modifiers(ITEM_MOD)
		names = [g["group_name"] for g in groups]
		self.assertIn(G_SIZE, names)
		self.assertIn(G_EXTRAS, names)
		self.assertNotIn(G_DISABLED, names)  # disabled excluded
		# price_delta exposed for display
		size = next(g for g in groups if g["group_name"] == G_SIZE)
		large = next(o for o in size["options"] if o["label"] == "Large")
		self.assertEqual(flt(large["price_delta"]), 5.0)

	def test_full_map_when_item_omitted(self):
		full = get_item_modifiers()
		self.assertIsInstance(full, dict)
		self.assertIn(ITEM_MOD, full)
		self.assertTrue(full[ITEM_MOD])
		# item with no groups is absent from the map, or maps to []
		self.assertFalse(full.get(ITEM_PLAIN))

	def test_item_without_groups_returns_empty(self):
		self.assertEqual(get_item_modifiers(ITEM_PLAIN), [])

	def test_endpoint_is_whitelisted_and_not_guest(self):
		# staff-only: must be whitelisted, must NOT be guest-accessible
		self.assertIn(get_item_modifiers, frappe.whitelisted)
		self.assertNotIn(get_item_modifiers, frappe.guest_methods)

	def test_plain_authenticated_cashier_can_resolve(self):
		# internal resolvers use frappe.get_all/get_cached_doc (perms bypassed by
		# design) so a cashier without write on the modifier doctypes can still price.
		email = "_test_mod_cashier@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "ModCashier",
					"send_welcome_email": 0,
					"roles": [{"role": "POSNext Cashier"}],
				}
			).insert(ignore_permissions=True)
		try:
			frappe.set_user(email)
			groups = get_item_modifiers(ITEM_MOD)
			self.assertTrue(groups)
		finally:
			frappe.set_user("Administrator")


# ══════════════════════════════════════════════════════════════════════
#  session_add_item  with modifiers  (integration)
# ══════════════════════════════════════════════════════════════════════
class TestSessionAddItemModifiers(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_setup_modifier_fixtures()

	def tearDown(self):
		_close_open_sessions()

	def _open(self):
		return get_session(TABLE, create=1)

	# ---- additive no-modifier regression ----
	def test_no_modifier_call_unchanged(self):
		s = self._open()
		out = session_add_item(s["name"], ITEM_PLAIN, qty=2)
		line = out["items"][0]
		self.assertEqual(flt(line["rate"]), 10.0)
		self.assertEqual(flt(line["amount"]), 20.0)
		self.assertEqual(line["notes"], "")
		self.assertEqual(flt(out["grand_total"]), 20.0)

	def test_empty_modifier_matches_no_modifier(self):
		# item with no groups prices identically with or without a spurious empty selection
		s = self._open()
		out_none = session_add_item(s["name"], ITEM_PLAIN, qty=1)
		s2 = self._open()  # same open session
		out_empty = session_add_item(s2["name"], ITEM_PLAIN, qty=1, modifiers={})
		self.assertEqual(flt(out_none["items"][0]["rate"]), flt(out_empty["items"][0]["rate"]))
		self.assertEqual(out_empty["items"][0]["notes"], "")

	# ---- rate = base + deltas, note carries summary ----
	def test_modifier_call_sets_rate_and_note(self):
		s = self._open()
		out = session_add_item(
			s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Large", G_EXTRAS: ["Extra Shot"]}
		)
		line = out["items"][0]
		self.assertEqual(flt(line["rate"]), 18.0)  # 10 + 5 + 3
		self.assertEqual(flt(line["amount"]), 18.0)
		self.assertEqual(line["notes"], "Large · Extra Shot")

	def test_modifier_note_folds_freetext_notes(self):
		s = self._open()
		out = session_add_item(
			s["name"], ITEM_MOD, qty=1, notes="No sugar", modifiers={G_SIZE: "Large"}
		)
		self.assertEqual(out["items"][0]["notes"], "Large · No sugar")

	# ---- distinct selection -> distinct line; identical -> merge ----
	def test_distinct_selection_makes_distinct_lines(self):
		s = self._open()
		session_add_item(s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Regular"})
		out = session_add_item(s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Large"})
		self.assertEqual(len(out["items"]), 2)
		notes = sorted(i["notes"] for i in out["items"])
		self.assertEqual(notes, ["Large", "Regular"])
		rates = sorted(flt(i["rate"]) for i in out["items"])
		self.assertEqual(rates, [10.0, 15.0])

	def test_identical_selection_merges_qty(self):
		s = self._open()
		session_add_item(s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Large"})
		out = session_add_item(s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Large"})
		self.assertEqual(len(out["items"]), 1)
		self.assertEqual(flt(out["items"][0]["qty"]), 2)
		self.assertEqual(flt(out["items"][0]["rate"]), 15.0)

	# ---- trust boundary at the session layer ----
	def test_stored_rate_depends_only_on_server_config(self):
		s = self._open()
		out = session_add_item(s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Large"})
		# even qty as a stringy value is coerced; rate never comes from the client
		self.assertEqual(flt(out["items"][0]["rate"]), 15.0)

	# ---- disabled item rejected at base resolution regardless of modifiers ----
	def test_disabled_item_throws_before_pricing(self):
		s = self._open()
		with self.assertRaises(frappe.ValidationError):
			session_add_item(s["name"], ITEM_DISABLED, qty=1, modifiers={G_SIZE: "Regular"})

	# ---- validation still throws through the session entry point ----
	def test_required_group_throws_through_session(self):
		s = self._open()
		with self.assertRaises(frappe.ValidationError):
			session_add_item(s["name"], ITEM_MOD, qty=1, modifiers={})  # Size required

	# ---- note flows to the KOT ----
	def test_modifier_note_flows_to_kot(self):
		s = self._open()
		session_add_item(
			s["name"], ITEM_MOD, qty=1, modifiers={G_SIZE: "Large", G_EXTRAS: ["Extra Shot"]}
		)
		res = session_send_kitchen(s["name"])
		kot = frappe.get_doc("KOT Ticket", res["kot"])
		kot_notes = [i.notes for i in kot.items if i.item_code == ITEM_MOD]
		self.assertTrue(any("Large" in (n or "") and "Extra Shot" in (n or "") for n in kot_notes))


# ══════════════════════════════════════════════════════════════════════
#  Restaurant desk Workspace (fixture)
# ══════════════════════════════════════════════════════════════════════
class TestRestaurantWorkspace(FrappeTestCase):
	def test_workspace_exists_after_migrate(self):
		self.assertTrue(frappe.db.exists("Workspace", "Restaurant"))

	def test_workspace_module_is_restaurant(self):
		self.assertEqual(
			frappe.db.get_value("Workspace", "Restaurant", "module"), "Restaurant"
		)

	def test_workspace_is_public_and_singular(self):
		from frappe.utils import cint

		self.assertEqual(cint(frappe.db.get_value("Workspace", "Restaurant", "public")), 1)
		# name is the PK -> re-migrate can never duplicate; assert exactly one row
		rows = frappe.get_all("Workspace", filters={"name": "Restaurant"})
		self.assertEqual(len(rows), 1)


# ══════════════════════════════════════════════════════════════════════
#  Seed patch  seed_restaurant_modifiers  (idempotency + production-safety)
# ══════════════════════════════════════════════════════════════════════
class TestSeedRestaurantModifiers(FrappeTestCase):
	def _execute_patch(self):
		import importlib

		mod = importlib.import_module("pos_next.patches.v2_0_0.seed_restaurant_modifiers")
		mod.execute()

	def _option_labels(self, group):
		return frappe.get_all(
			"POS Modifier Option",
			filters={"parent": group, "parenttype": "POS Modifier Group", "parentfield": "options"},
			pluck="option_label",
			order_by="idx asc",
		)

	def test_run_twice_no_duplicate_groups(self):
		self._execute_patch()
		self._execute_patch()
		self.assertTrue(frappe.db.exists("POS Modifier Group", "Size"))
		self.assertTrue(frappe.db.exists("POS Modifier Group", "Extras"))
		# name is unique, but assert the seed produced exactly these two named groups
		self.assertEqual(frappe.db.count("POS Modifier Group", {"name": "Size"}), 1)
		self.assertEqual(frappe.db.count("POS Modifier Group", {"name": "Extras"}), 1)

	def test_run_twice_no_duplicate_options(self):
		self._execute_patch()
		self._execute_patch()
		size_opts = self._option_labels("Size")
		self.assertEqual(sorted(size_opts), ["Large", "Regular"])
		extras_opts = self._option_labels("Extras")
		self.assertEqual(sorted(extras_opts), ["Extra Shot", "Oat Milk", "Whipped Cream"])

	def test_attach_is_noop_without_demo_item(self):
		# production-safety: on a site without the demo ESPRESSO item the attach
		# step must be a clean no-op that raises nothing, even run twice.
		if frappe.db.exists("Item", "ESPRESSO"):
			frappe.delete_doc("Item", "ESPRESSO", force=1, ignore_permissions=True)
		try:
			self._execute_patch()
			self._execute_patch()
		except Exception as e:  # noqa: BLE001
			self.fail(f"seed patch raised on a site without ESPRESSO: {e}")
		self.assertFalse(frappe.db.exists("Item", "ESPRESSO"))

	def test_attach_to_demo_item_is_idempotent(self):
		# when the demo item DOES exist, both groups attach exactly once (no dup links)
		_ensure_item("ESPRESSO", rate=12)
		self._execute_patch()
		self._execute_patch()
		links = frappe.get_all(
			"POS Item Modifier",
			filters={"parent": "ESPRESSO", "parenttype": "Item", "parentfield": "custom_modifier_groups"},
			pluck="modifier_group",
		)
		self.assertEqual(sorted(set(links)), ["Extras", "Size"])
		self.assertEqual(len(links), 2)  # no duplicate rows

	def test_install_hook_seeds_groups(self):
		# F7: install-app marks patches complete without running them
		# (frappe/installer.py set_all_patches_as_completed), so the seed must also
		# fire from after_install. Assert the install-path wrapper creates the
		# sample groups. Idempotent -> safe even though pos_next is already
		# installed on the test site.
		from pos_next.install import seed_restaurant_modifiers

		seed_restaurant_modifiers(quiet=True)
		self.assertTrue(frappe.db.exists("POS Modifier Group", "Size"))
		self.assertTrue(frappe.db.exists("POS Modifier Group", "Extras"))

	def test_seeded_groups_price_correctly(self):
		self._execute_patch()
		_ensure_item("ESPRESSO", rate=12)
		self._execute_patch()  # attaches Size + Extras to ESPRESSO
		rate, _sel, note = _price_with_modifiers(
			"ESPRESSO", 12, {"Size": "Large", "Extras": ["Extra Shot"]}
		)
		self.assertEqual(flt(rate), 20.0)  # 12 + 5 (Large) + 3 (Extra Shot)
		self.assertIn("Large", note)
		self.assertIn("Extra Shot", note)
