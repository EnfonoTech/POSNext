# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

"""
TDD test suite (pre-implementation) for the NEW whitelisted endpoint
`pos_next.api.restaurant.get_modifier_selection` — the server-authoritative,
DELTA-ONLY modifier pricing used by the dine-in main cart.

Spec: .pipeline/spec.md  §"Backend — get_modifier_selection" + Q2 (LOCKED:
delta-only) + Test Plan "Backend (pos_next FrappeTestCase)".

Contract:
    @frappe.whitelist()
    def get_modifier_selection(item_code, modifiers=None) ->
        { "delta": <flt>, "note": <str>, "validated": <dict> }

  * delta  = sum of the SELECTED option price_delta values ONLY (NOT base+delta) —
             the main cart owns the base rate (Q2). This is the whole point of the
             endpoint: server-authoritative modifier contribution + validation
             WITHOUT a second base-price source of truth.
  * note   = the ' · '-joined selected labels in configuration order (MODIFIER_SEP).
  * validated = {group_name: [chosen labels]} in config order.
  * validation parity with _price_with_modifiers: required / min / max / single /
             unknown group / foreign option / disabled group / disabled option.
  * empty/None selection with no required group -> delta 0, note "", empty validated.

The module-level import of the not-yet-existing endpoint raises ImportError until
implemented, so the whole suite reports RED — the correct pre-implementation TDD
signal. Fixture setup is reused from test_restaurant.py to stay in lock-step with
the modifier config the rest of the feature is tested against.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

# Does NOT exist yet -> ImportError until implemented (correct RED state).
from pos_next.api.restaurant import get_modifier_selection

# Reuse the exact modifier fixtures + identifiers from the existing suite.
from pos_next.api.test_restaurant import (
	G_DISABLED,
	G_EXTRAS,
	G_MINTWO,
	G_SIZE,
	ITEM_MOD,
	ITEM_OPT,
	ITEM_PLAIN,
	_setup_modifier_fixtures,
)


class TestGetModifierSelection(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_setup_modifier_fixtures()

	# ── shape ──────────────────────────────────────────────────────────
	def test_returns_delta_note_validated_keys(self):
		res = get_modifier_selection(ITEM_MOD, {G_SIZE: "Large"})
		for key in ("delta", "note", "validated"):
			self.assertIn(key, res)

	# ── delta-only pricing (Q2): NOT base+delta ────────────────────────
	def test_delta_is_modifier_contribution_only(self):
		res = get_modifier_selection(ITEM_MOD, {G_SIZE: "Large"})
		# server delta only — base (10) must NOT be included
		self.assertEqual(flt(res["delta"]), 5.0)
		self.assertNotEqual(flt(res["delta"]), 15.0)
		self.assertEqual(res["note"], "Large")

	def test_delta_sums_single_plus_multiple(self):
		res = get_modifier_selection(
			ITEM_MOD, {G_SIZE: "Regular", G_EXTRAS: ["Extra Shot", "Oat Milk"]}
		)
		# 0 (Regular) + 3 (Extra Shot) + 2.5 (Oat Milk)
		self.assertEqual(flt(res["delta"]), 5.5)

	def test_zero_delta_selection(self):
		res = get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular"})
		self.assertEqual(flt(res["delta"]), 0.0)
		self.assertEqual(res["note"], "Regular")

	def test_max_select_zero_is_unlimited(self):
		res = get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular", G_MINTWO: ["MA", "MB", "MC"]})
		# 0 + 1.5 + 0.25 + 4.0
		self.assertEqual(flt(res["delta"]), 5.75)

	# ── note ordering + validated map ──────────────────────────────────
	def test_note_and_validated_follow_config_order(self):
		res = get_modifier_selection(
			ITEM_MOD, {G_SIZE: "Regular", G_EXTRAS: ["Whipped Cream", "Extra Shot"]}
		)
		# note is config-ordered regardless of client order
		self.assertEqual(res["note"], "Regular · Extra Shot · Whipped Cream")
		self.assertEqual(res["validated"][G_SIZE], ["Regular"])
		self.assertEqual(res["validated"][G_EXTRAS], ["Extra Shot", "Whipped Cream"])

	# ── input coercion ─────────────────────────────────────────────────
	def test_accepts_json_string_selection(self):
		sel = json.dumps({G_SIZE: "Large", G_EXTRAS: ["Extra Shot"]})
		res = get_modifier_selection(ITEM_MOD, sel)
		self.assertEqual(flt(res["delta"]), 8.0)  # 5 + 3
		self.assertEqual(res["note"], "Large · Extra Shot")

	# ── empty / None selection ─────────────────────────────────────────
	def test_empty_selection_returns_zero_delta(self):
		for empty in (None, {}, ""):
			res = get_modifier_selection(ITEM_OPT, empty)
			self.assertEqual(flt(res["delta"]), 0.0)
			self.assertEqual(res["note"], "")
			self.assertFalse(res["validated"])

	def test_item_without_groups_empty_selection(self):
		res = get_modifier_selection(ITEM_PLAIN, {})
		self.assertEqual(flt(res["delta"]), 0.0)
		self.assertEqual(res["note"], "")

	# ── validation throws (parity with _price_with_modifiers) ──────────
	def test_required_group_missing_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {})  # Size required

	def test_single_with_two_picks_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: ["Regular", "Large"]})

	def test_below_min_select_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular", G_MINTWO: ["MA"]})

	def test_above_max_select_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(
				ITEM_MOD, {G_SIZE: "Regular", G_EXTRAS: ["Extra Shot", "Whipped Cream", "Oat Milk"]}
			)

	def test_unknown_group_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular", "No Such Group": "X"})

	def test_foreign_option_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular", G_EXTRAS: ["Large"]})

	def test_disabled_group_selection_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular", G_DISABLED: "DX"})

	def test_disabled_option_selection_throws(self):
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: "Regular", G_EXTRAS: ["Truffle"]})

	# ── trust boundary: delta is server-derived only ───────────────────
	def test_delta_is_server_derived_only(self):
		res = get_modifier_selection(ITEM_MOD, {G_SIZE: "Large"})
		self.assertEqual(flt(res["delta"]), 5.0)  # exactly the server delta
		# a fabricated numeric label is just an unknown option
		with self.assertRaises(frappe.ValidationError):
			get_modifier_selection(ITEM_MOD, {G_SIZE: "999"})

	# ── endpoint exposure ──────────────────────────────────────────────
	def test_endpoint_is_whitelisted_and_not_guest(self):
		self.assertIn(get_modifier_selection, frappe.whitelisted)
		self.assertNotIn(get_modifier_selection, frappe.guest_methods)
