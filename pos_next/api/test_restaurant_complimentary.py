# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

"""
TDD suite (pre-implementation) — Feature 1: Complimentary / Void order.

Written BEFORE the implementation exists — every test here MUST currently FAIL
(the module-level import of the not-yet-existing endpoints raises ImportError,
so the whole file reports RED) and MUST PASS once the spec in
.pipeline/spec.md is implemented.

Encodes the LOCKED gate decisions (spec §"Human gate decisions (LOCKED)"):
  - Timing (Q1) = stock issued AT CREATION (Pending); Reject cancels the Stock
    Entry (Kaapqah model). Idempotent — never double-issue, re-reject is a no-op.
  - Stock model (Q2) = BOTH: is_stock_item==1 -> Material Issue that item
    directly; a non-stock menu item -> consume its DEFAULT BOM raw materials via
    a Material Issue. Non-stock item with NO default BOM -> zero stock movement,
    no throw. One Stock Entry per comp (idempotency link custom_pos_comp_order).
  - Whole-order comp; NO Sales Invoice ever (nothing to ZATCA).
  - Warehouse = POS Profile.warehouse; cost_center = POS Profile.cost_center ->
    Company.cost_center.
  - Approvers = System Manager / Sales Manager / Nexus POS Manager;
    POSNext Cashier = create-only (cannot approve, no doctype write perm).

Covers the spec "Test Plan" (backend) + "Edge Cases (Feature 1)":
  stock reversal (direct + BOM), idempotency, stock-item-only vs BOM,
  no-invoice, permissions, reject->stock back, transition guards, total math,
  missing-price no-throw, validation.
"""

import frappe
from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint, flt

# ── RED trigger ────────────────────────────────────────────────────────
# None of these exist yet -> ImportError until implemented (correct RED state).
from pos_next.api.restaurant import (
	_comp_reverse_stock,
	_comp_stock_return,
	approve_complimentary_order,
	submit_complimentary_order,
)

# ── fixture identifiers ────────────────────────────────────────────────
STOCK_ITEM = "_COMP_STOCK_ITEM"      # is_stock_item=1, rate 20 -> Material Issue directly
BOM_ITEM = "_COMP_BOM_ITEM"          # non-stock menu item, has a default BOM
NOBOM_ITEM = "_COMP_NOBOM_ITEM"      # non-stock menu item, NO default BOM -> no stock move
RAW_ITEM = "_COMP_RAW_ITEM"          # is_stock_item=1, raw material consumed by BOM_ITEM
NOPRICE_ITEM = "_COMP_NOPRICE_ITEM"  # non-stock, no price -> comp must not hard-fail
BOMNS_ITEM = "_COMP_BOMNS_ITEM"      # non-stock menu item; default BOM mixes a stock + a NON-stock raw
NONSTOCK_RAW = "_COMP_NONSTOCK_RAW"  # non-stock BOM raw -> must be dropped, not abort the whole issue

BOM_RAW_QTY = 3.0                    # raw units per one BOM_ITEM
NONSTOCK_RAW_QTY = 5.0              # non-stock raw units per one BOMNS_ITEM (dropped from the issue)

CASHIER = "_comp_cashier@example.com"        # POSNext Cashier — create only
MANAGER = "_comp_manager@example.com"        # Sales Manager — approver

COMP_DT = "POS Complimentary Order"


def _company():
	if frappe.db.exists("Company", "_Test Company"):
		return "_Test Company"
	return frappe.defaults.get_global_default("company") or frappe.db.get_value(
		"Company", {"name": ["!=", ""]}, "name"
	)


def _warehouse(company):
	if company == "_Test Company" and frappe.db.exists("Warehouse", "_Test Warehouse - _TC"):
		return "_Test Warehouse - _TC"
	return frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name", order_by="creation asc"
	)


def _cost_center(company):
	return frappe.get_cached_value("Company", company, "cost_center") or frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0, "disabled": 0}, "name", order_by="creation asc"
	)


def _item_group():
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"


def _price_list():
	return "Standard Selling" if frappe.db.exists("Price List", "Standard Selling") else frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1}, "name"
	)


def _ensure_item(code, *, is_stock, rate=0):
	if not frappe.db.exists("Item", code):
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": _item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 1 if is_stock else 0,
				"is_sales_item": 1,
				"standard_rate": rate,
			}
		)
		doc.flags.from_integration = True
		doc.insert(ignore_permissions=True)


def _ensure_default_bom(menu_item, raw_item, company, warehouse):
	"""One submitted, default BOM: menu_item <- BOM_RAW_QTY x raw_item."""
	if frappe.db.exists("BOM", {"item": menu_item, "is_default": 1, "docstatus": 1}):
		return
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": menu_item,
			"company": company,
			"quantity": 1,
			"is_active": 1,
			"is_default": 1,
			"rm_cost_as_per": "Valuation Rate",
			"items": [
				{
					"item_code": raw_item,
					"qty": BOM_RAW_QTY,
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"source_warehouse": warehouse,
					"rate": 0,
				}
			],
		}
	)
	bom.insert(ignore_permissions=True)
	bom.submit()


def _ensure_default_bom_multi(menu_item, raws, company, warehouse):
	"""One submitted, default BOM: menu_item <- [(raw_item, qty), ...]. `raws` may include
	NON-stock items (used to prove the comp reversal drops them instead of aborting)."""
	if frappe.db.exists("BOM", {"item": menu_item, "is_default": 1, "docstatus": 1}):
		return
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": menu_item,
			"company": company,
			"quantity": 1,
			"is_active": 1,
			"is_default": 1,
			"rm_cost_as_per": "Valuation Rate",
			"items": [
				{
					"item_code": rc,
					"qty": q,
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"source_warehouse": warehouse,
					"rate": 0,
				}
				for rc, q in raws
			],
		}
	)
	bom.insert(ignore_permissions=True)
	bom.submit()


def _ensure_profile(company, warehouse):
	name = "_COMP_TEST_PROFILE"
	cc = _cost_center(company)
	if frappe.db.exists("POS Profile", name):
		doc = frappe.get_doc("POS Profile", name)
		doc.warehouse = warehouse
		doc.cost_center = cc
		doc.selling_price_list = _price_list()
		if hasattr(doc, "restaurant_mode"):
			doc.restaurant_mode = 1
		# Skip erpnext POS Profile.validate() (payment-method / MoP-account setup) and the
		# mandatory-field recheck on re-save — the comp/stock code only reads
		# company/warehouse/cost_center/price_list off it.
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		return name
	doc = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": name,
			"company": company,
			"warehouse": warehouse,
			"cost_center": cc,
			"selling_price_list": _price_list(),
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"disabled": 0,
		}
	)
	if hasattr(doc, "restaurant_mode"):
		doc.restaurant_mode = 1
	doc.flags.ignore_mandatory = True
	# Skip erpnext POS Profile.validate() (requires payment methods + MoP company accounts);
	# this fixture only needs the profile's link fields for stock/price resolution.
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	return name


def _ensure_user(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
	else:
		u = frappe.get_doc("User", email)
		if role not in [r.role for r in u.roles]:
			u.append("roles", {"role": role})
			u.save(ignore_permissions=True)


def _bin_qty(item_code, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def _stock_entries_for(comp_name, docstatus=1):
	return frappe.get_all(
		"Stock Entry",
		filters={"custom_pos_comp_order": comp_name, "docstatus": docstatus},
		pluck="name",
	)


def _comp_name(res):
	"""Tolerant extractor for the created comp doc name (ASSUMED return key —
	documented in test-results.md). Falls back to the most-recent comp doc."""
	if isinstance(res, dict):
		for k in ("comp_order", "complimentary_order", "name", "free_order"):
			if res.get(k):
				return res[k]
	return frappe.db.get_value(COMP_DT, {}, "name", order_by="creation desc")


class _CompBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = _company()
		cls.warehouse = _warehouse(cls.company)
		cls.profile = _ensure_profile(cls.company, cls.warehouse)

		_ensure_item(STOCK_ITEM, is_stock=True, rate=20)
		_ensure_item(RAW_ITEM, is_stock=True, rate=2)
		_ensure_item(BOM_ITEM, is_stock=False, rate=15)
		_ensure_item(NOBOM_ITEM, is_stock=False, rate=12)
		_ensure_item(NOPRICE_ITEM, is_stock=False, rate=0)
		_ensure_item(BOMNS_ITEM, is_stock=False, rate=18)
		_ensure_item(NONSTOCK_RAW, is_stock=False, rate=1)
		_ensure_default_bom(BOM_ITEM, RAW_ITEM, cls.company, cls.warehouse)
		# BOMNS_ITEM's default BOM mixes a stock raw (RAW_ITEM) and a NON-stock raw
		# (NONSTOCK_RAW) so the reversal must drop the latter and still issue the former.
		_ensure_default_bom_multi(
			BOMNS_ITEM,
			[(RAW_ITEM, BOM_RAW_QTY), (NONSTOCK_RAW, NONSTOCK_RAW_QTY)],
			cls.company,
			cls.warehouse,
		)

		# Top up stock so a Material Issue deterministically reduces the bin
		# (rather than driving it negative / blocking).
		for code in (STOCK_ITEM, RAW_ITEM):
			if _bin_qty(code, cls.warehouse) < 100:
				try:
					make_stock_entry(
						item_code=code, target=cls.warehouse, qty=200, rate=5, company=cls.company
					)
				except Exception:
					frappe.db.rollback()

		_ensure_user(CASHIER, "POSNext Cashier")
		_ensure_user(MANAGER, "Sales Manager")

	def tearDown(self):
		frappe.set_user("Administrator")
		# Best-effort cleanup: submit_complimentary_order commits, so unwind the
		# test comps + their Stock Entries to keep the suite re-runnable.
		for name in frappe.get_all(COMP_DT, pluck="name"):
			for se in frappe.get_all(
				"Stock Entry", filters={"custom_pos_comp_order": name, "docstatus": 1}, pluck="name"
			):
				try:
					frappe.get_doc("Stock Entry", se).cancel()
				except Exception:
					pass
			try:
				frappe.delete_doc(COMP_DT, name, force=1, ignore_permissions=True)
			except Exception:
				pass
		frappe.db.commit()


# ══════════════════════════════════════════════════════════════════════
#  Stock reversal — direct (is_stock_item) + BOM (non-stock)
# ══════════════════════════════════════════════════════════════════════
class TestCompStockReversal(_CompBase):
	def test_stock_item_creates_one_material_issue(self):
		before = _bin_qty(STOCK_ITEM, self.warehouse)
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 2}],
			reason="Staff Meal",
			pos_profile=self.profile,
		)
		comp = _comp_name(res)
		ses = _stock_entries_for(comp)
		self.assertEqual(len(ses), 1)  # exactly one submitted Stock Entry
		se = frappe.get_doc("Stock Entry", ses[0])
		self.assertEqual(se.stock_entry_type, "Material Issue")
		self.assertEqual(se.purpose, "Material Issue")
		# direct issue of the stock item from the profile warehouse
		lines = {r.item_code: r for r in se.items}
		self.assertIn(STOCK_ITEM, lines)
		self.assertEqual(flt(lines[STOCK_ITEM].qty), 2.0)
		self.assertEqual(lines[STOCK_ITEM].s_warehouse, self.warehouse)
		# Bin decreased by exactly the comped qty
		self.assertEqual(_bin_qty(STOCK_ITEM, self.warehouse), before - 2.0)

	def test_non_stock_item_consumes_default_bom_raw(self):
		raw_before = _bin_qty(RAW_ITEM, self.warehouse)
		res = submit_complimentary_order(
			items=[{"item_code": BOM_ITEM, "qty": 2}],
			reason="Wastage / Spillage",
			pos_profile=self.profile,
		)
		comp = _comp_name(res)
		ses = _stock_entries_for(comp)
		self.assertEqual(len(ses), 1)
		se = frappe.get_doc("Stock Entry", ses[0])
		codes = {r.item_code for r in se.items}
		# raw material consumed; the non-stock menu item is NOT itself issued
		self.assertIn(RAW_ITEM, codes)
		self.assertNotIn(BOM_ITEM, codes)
		raw_line = next(r for r in se.items if r.item_code == RAW_ITEM)
		self.assertEqual(flt(raw_line.qty), BOM_RAW_QTY * 2)  # 3 x 2 = 6
		self.assertEqual(_bin_qty(RAW_ITEM, self.warehouse), raw_before - BOM_RAW_QTY * 2)

	def test_non_stock_without_bom_moves_no_stock_and_does_not_throw(self):
		res = submit_complimentary_order(
			items=[{"item_code": NOBOM_ITEM, "qty": 1}],
			reason="Management",
			pos_profile=self.profile,
		)
		comp = _comp_name(res)
		self.assertTrue(frappe.db.exists(COMP_DT, comp))     # comp still recorded
		self.assertEqual(_stock_entries_for(comp), [])       # no stock movement

	def test_mixed_order_single_stock_entry_direct_and_bom(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}, {"item_code": BOM_ITEM, "qty": 1}],
			reason="Customer Complaint",
			pos_profile=self.profile,
		)
		comp = _comp_name(res)
		ses = _stock_entries_for(comp)
		self.assertEqual(len(ses), 1)  # ONE Stock Entry for the whole comp
		codes = {r.item_code for r in frappe.get_doc("Stock Entry", ses[0]).items}
		self.assertIn(STOCK_ITEM, codes)   # direct stock line
		self.assertIn(RAW_ITEM, codes)     # BOM raw line
		self.assertNotIn(BOM_ITEM, codes)  # non-stock menu item never issued

	def test_non_stock_bom_raw_is_dropped_reversal_not_lost(self):
		# Reviewer #2: a single non-stock BOM raw must NOT abort the whole Material Issue
		# (which used to be swallowed by the broad except -> stock_entry=None, valid lines
		# silently lost). The non-stock raw is dropped + logged; the stock raw still issues.
		raw_before = _bin_qty(RAW_ITEM, self.warehouse)
		res = submit_complimentary_order(
			items=[{"item_code": BOMNS_ITEM, "qty": 1}],
			reason="Wastage / Spillage",
			pos_profile=self.profile,
		)
		comp = _comp_name(res)
		ses = _stock_entries_for(comp)
		self.assertEqual(len(ses), 1)  # reversal survives despite the non-stock raw
		self.assertIsNone(res.get("stock_warning"))  # a valid SE was created -> no warning
		se = frappe.get_doc("Stock Entry", ses[0])
		codes = {r.item_code for r in se.items}
		self.assertIn(RAW_ITEM, codes)          # valid stock raw issued
		self.assertNotIn(NONSTOCK_RAW, codes)   # non-stock raw dropped, not in the issue
		raw_line = next(r for r in se.items if r.item_code == RAW_ITEM)
		self.assertEqual(flt(raw_line.qty), BOM_RAW_QTY)  # 3 x 1
		self.assertEqual(_bin_qty(RAW_ITEM, self.warehouse), raw_before - BOM_RAW_QTY)

	def test_mixed_direct_survives_alongside_non_stock_bom_raw(self):
		# The direct stock line must survive even when a comped BOM item drags in a
		# non-stock raw — the exact "entire Material Issue silently lost" bug (Reviewer #2).
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}, {"item_code": BOMNS_ITEM, "qty": 1}],
			reason="Management",
			pos_profile=self.profile,
		)
		comp = _comp_name(res)
		ses = _stock_entries_for(comp)
		self.assertEqual(len(ses), 1)
		codes = {r.item_code for r in frappe.get_doc("Stock Entry", ses[0]).items}
		self.assertIn(STOCK_ITEM, codes)        # direct stock line NOT lost
		self.assertIn(RAW_ITEM, codes)          # BOM stock raw issued
		self.assertNotIn(NONSTOCK_RAW, codes)   # non-stock raw dropped


# ══════════════════════════════════════════════════════════════════════
#  Idempotency  (double-click / retry / re-submit never double-issues)
# ══════════════════════════════════════════════════════════════════════
class TestCompIdempotency(_CompBase):
	def test_reverse_stock_twice_yields_one_entry(self):
		before = _bin_qty(STOCK_ITEM, self.warehouse)
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 2}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		# A re-fire (retry / double click) must be a no-op: the guard on the
		# custom_pos_comp_order link + docstatus=1 stops a second Material Issue.
		second = _comp_reverse_stock(comp, self.profile)
		self.assertIsNone(second)
		self.assertEqual(len(_stock_entries_for(comp)), 1)
		self.assertEqual(_bin_qty(STOCK_ITEM, self.warehouse), before - 2.0)  # decreased once

	def test_same_idempotency_key_creates_one_comp(self):
		# Reviewer #4: two rapid submits carrying the SAME client key must create ONE comp
		# and ONE Material Issue (no double stock depletion) — the endpoint double-submit
		# guard, distinct from the _comp_reverse_stock re-fire guard above.
		before = _bin_qty(STOCK_ITEM, self.warehouse)
		key = "IDEMP-TEST-KEY-1"
		r1 = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 2}],
			reason="Staff Meal",
			pos_profile=self.profile,
			idempotency_key=key,
		)
		r2 = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 2}],
			reason="Staff Meal",
			pos_profile=self.profile,
			idempotency_key=key,
		)
		self.assertEqual(_comp_name(r1), _comp_name(r2))  # the replay returns the winner
		self.assertTrue(r2.get("replayed"))
		self.assertEqual(len(frappe.get_all(COMP_DT, filters={"idempotency_key": key})), 1)
		comp = _comp_name(r1)
		self.assertEqual(len(_stock_entries_for(comp)), 1)  # one Material Issue
		self.assertEqual(_bin_qty(STOCK_ITEM, self.warehouse), before - 2.0)  # depleted once


# ══════════════════════════════════════════════════════════════════════
#  No Sales Invoice — ever  (nothing reaches ZATCA)
# ══════════════════════════════════════════════════════════════════════
class TestCompNoInvoice(_CompBase):
	def test_comp_creates_no_sales_invoice(self):
		si_before = frappe.db.count("Sales Invoice")
		submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Marketing / Promo", pos_profile=self.profile
		)
		self.assertEqual(frappe.db.count("Sales Invoice"), si_before)  # zero new SI


# ══════════════════════════════════════════════════════════════════════
#  Permissions  (Cashier create-only; approver roles approve)
# ══════════════════════════════════════════════════════════════════════
class TestCompPermissions(_CompBase):
	def test_cashier_role_has_no_write_on_doctype(self):
		# doctype-level guard: POSNext Cashier can create + read, NOT write.
		perms = frappe.get_all(
			"DocPerm",
			filters={"parent": COMP_DT, "role": "POSNext Cashier"},
			fields=["`read`", "`write`", "`create`"],
		) or frappe.get_all(
			"Custom DocPerm",
			filters={"parent": COMP_DT, "role": "POSNext Cashier"},
			fields=["`read`", "`write`", "`create`"],
		)
		self.assertTrue(perms, "POSNext Cashier must have a perm row on the comp doctype")
		row = perms[0]
		self.assertTrue(cint(row.get("create")))
		self.assertTrue(cint(row.get("read")))
		self.assertFalse(cint(row.get("write")))

	def test_cashier_can_create_comp(self):
		frappe.set_user(CASHIER)
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		self.assertTrue(frappe.db.exists(COMP_DT, comp))
		self.assertEqual(frappe.db.get_value(COMP_DT, comp, "status"), "Pending")
		self.assertEqual(frappe.db.get_value(COMP_DT, comp, "staff"), CASHIER)

	def test_cashier_cannot_approve(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		frappe.set_user(CASHIER)
		with self.assertRaises(frappe.PermissionError):
			approve_complimentary_order(comp, "Approved")

	def test_sales_manager_can_approve(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		frappe.set_user(MANAGER)
		approve_complimentary_order(comp, "Approved")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(COMP_DT, comp, "status"), "Approved")
		self.assertEqual(frappe.db.get_value(COMP_DT, comp, "approved_by"), MANAGER)
		self.assertTrue(frappe.db.get_value(COMP_DT, comp, "approved_on"))


# ══════════════════════════════════════════════════════════════════════
#  Reject -> stock returned  (+ re-reject is a no-op)
# ══════════════════════════════════════════════════════════════════════
class TestCompReject(_CompBase):
	def test_reject_cancels_stock_entry_and_restores_bin(self):
		before = _bin_qty(STOCK_ITEM, self.warehouse)
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 2}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		self.assertEqual(_bin_qty(STOCK_ITEM, self.warehouse), before - 2.0)  # issued at creation
		frappe.set_user(MANAGER)
		approve_complimentary_order(comp, "Rejected")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(COMP_DT, comp, "status"), "Rejected")
		self.assertEqual(_stock_entries_for(comp, docstatus=1), [])  # SE cancelled
		self.assertEqual(_bin_qty(STOCK_ITEM, self.warehouse), before)  # stock back

	def test_re_reject_is_noop(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		_comp_stock_return(comp)
		# already cancelled -> second call must not raise / must not touch anything
		_comp_stock_return(comp)
		self.assertEqual(_stock_entries_for(comp, docstatus=1), [])


# ══════════════════════════════════════════════════════════════════════
#  Transition guards  (only Pending -> Approved / Rejected)
# ══════════════════════════════════════════════════════════════════════
class TestCompTransitions(_CompBase):
	def test_cannot_redecide_after_approved(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		frappe.set_user(MANAGER)
		approve_complimentary_order(comp, "Approved")
		with self.assertRaises(frappe.ValidationError):
			approve_complimentary_order(comp, "Rejected")  # terminal -> illegal

	def test_invalid_decision_value_throws(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 1}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		frappe.set_user(MANAGER)
		with self.assertRaises(frappe.ValidationError):
			approve_complimentary_order(comp, "Maybe")


# ══════════════════════════════════════════════════════════════════════
#  Money math + validation + resilience
# ══════════════════════════════════════════════════════════════════════
class TestCompValueAndValidation(_CompBase):
	def test_total_value_equals_sum_qty_rate(self):
		res = submit_complimentary_order(
			items=[{"item_code": STOCK_ITEM, "qty": 2, "rate": 20}], reason="Staff Meal", pos_profile=self.profile
		)
		comp = _comp_name(res)
		self.assertEqual(flt(frappe.db.get_value(COMP_DT, comp, "total_value")), 40.0)

	def test_empty_items_throws(self):
		with self.assertRaises(frappe.ValidationError):
			submit_complimentary_order(items=[], reason="Staff Meal", pos_profile=self.profile)

	def test_missing_reason_throws(self):
		with self.assertRaises(frappe.ValidationError):
			submit_complimentary_order(
				items=[{"item_code": STOCK_ITEM, "qty": 1}], reason=None, pos_profile=self.profile
			)

	def test_missing_price_does_not_hard_fail(self):
		# free-order rate is display-only -> fall back to standard_rate/0, never throw
		res = submit_complimentary_order(
			items=[{"item_code": NOPRICE_ITEM, "qty": 1}], reason="Other", pos_profile=self.profile
		)
		comp = _comp_name(res)
		self.assertTrue(frappe.db.exists(COMP_DT, comp))
		self.assertEqual(frappe.db.get_value(COMP_DT, comp, "status"), "Pending")
