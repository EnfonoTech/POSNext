# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

"""
TDD suite (pre-implementation) — Feature 3: Bilingual item names.

Unlike features 1 & 2 this feature adds no NEW backend symbol, so RED here is
driven by ASSERTIONS on not-yet-existing behaviour:
  - items.ITEM_RESULT_FIELDS gains "custom_arabic_name" (spec §63 / step 2).
  - Custom Field Item-custom_arabic_name exists (fixture, spec §106).
  - get_items payload carries custom_arabic_name (value when set, "" when unset).
  - restaurant.kot_send folds Arabic into item_name "EN · AR" via one batched
    Item.custom_arabic_name lookup (spec §64 / step 3); a byte-for-byte no-op
    when the field is empty.
  - The fold separator is MODIFIER_SEP (" · ").

Every value test sets Item.custom_arabic_name via frappe.db.set_value, which
raises until the fixture custom field is migrated — the correct RED signal.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api.items import ITEM_RESULT_FIELDS, get_items
from pos_next.api.restaurant import MODIFIER_SEP, kot_send

ITEM_AR = "_BILING_ITEM_AR"     # has an Arabic name -> folds
ITEM_EN = "_BILING_ITEM_EN"     # no Arabic name -> no-op
ARABIC = "لاتيه"


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


def _item_group():
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"


def _price_list():
	return "Standard Selling" if frappe.db.exists("Price List", "Standard Selling") else frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1}, "name"
	)


def _ensure_item(code):
	if not frappe.db.exists("Item", code):
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": _item_group(),
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"standard_rate": 10,
			}
		)
		doc.flags.from_integration = True
		doc.insert(ignore_permissions=True)


def _ensure_profile(company, warehouse):
	name = "_BILING_TEST_PROFILE"
	if frappe.db.exists("POS Profile", name):
		return name
	doc = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": name,
			"company": company,
			"warehouse": warehouse,
			"selling_price_list": _price_list(),
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"disabled": 0,
		}
	)
	doc.flags.ignore_mandatory = True
	# Skip erpnext POS Profile.validate() (payment-method / MoP-account setup); this
	# fixture only needs the profile for get_items' price-list resolution.
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	return name


class _BilingualBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = _company()
		cls.warehouse = _warehouse(cls.company)
		cls.profile = _ensure_profile(cls.company, cls.warehouse)
		_ensure_item(ITEM_AR)
		_ensure_item(ITEM_EN)
		# Set the Arabic name (raises until the fixture field is migrated -> RED).
		frappe.db.set_value("Item", ITEM_AR, "custom_arabic_name", ARABIC)
		frappe.db.set_value("Item", ITEM_EN, "custom_arabic_name", "")

	def tearDown(self):
		for name in frappe.get_all("KOT Ticket", filters={"status": "Open"}, pluck="name"):
			frappe.db.set_value("KOT Ticket", name, "status", "Cancelled", update_modified=False)
		frappe.db.commit()


# ══════════════════════════════════════════════════════════════════════
#  Custom field + item payload
# ══════════════════════════════════════════════════════════════════════
class TestBilingualPayload(_BilingualBase):
	def test_item_result_fields_includes_arabic(self):
		self.assertIn("custom_arabic_name", ITEM_RESULT_FIELDS)

	def test_custom_field_exists(self):
		self.assertTrue(frappe.db.exists("Custom Field", "Item-custom_arabic_name"))

	def test_get_items_payload_carries_arabic_when_set(self):
		rows = get_items(self.profile, search_term=ITEM_AR, limit=50)
		row = next((r for r in rows if r["item_code"] == ITEM_AR), None)
		self.assertIsNotNone(row)
		self.assertIn("custom_arabic_name", row)
		self.assertEqual(row["custom_arabic_name"], ARABIC)

	def test_get_items_payload_empty_when_unset(self):
		rows = get_items(self.profile, search_term=ITEM_EN, limit=50)
		row = next((r for r in rows if r["item_code"] == ITEM_EN), None)
		self.assertIsNotNone(row)
		# no-op: unset Arabic name comes back falsy, never the code / never None-crash
		self.assertIn("custom_arabic_name", row)
		self.assertFalse(row["custom_arabic_name"])


# ══════════════════════════════════════════════════════════════════════
#  KOT fold  (EN · AR)  — server-side, no KOT schema change
# ══════════════════════════════════════════════════════════════════════
class TestBilingualKotFold(_BilingualBase):
	def _kot_item_name(self, table_label, item_code, en_name):
		res = kot_send(
			table_label=table_label,
			items=[{"item_code": item_code, "item_name": en_name, "qty": 1, "notes": ""}],
			pos_profile=self.profile,
		)
		kot = frappe.get_doc("KOT Ticket", res["kot"])
		row = next(i for i in kot.items if i.item_code == item_code)
		return row.item_name

	def test_kot_folds_arabic_into_item_name(self):
		name = self._kot_item_name("T-BILING-1", ITEM_AR, "Latte")
		self.assertEqual(name, f"Latte{MODIFIER_SEP}{ARABIC}")

	def test_kot_uses_modifier_sep_separator(self):
		# the separator must be MODIFIER_SEP (" · "), consistent with the modifier note
		name = self._kot_item_name("T-BILING-2", ITEM_AR, "Latte")
		self.assertEqual(MODIFIER_SEP, " · ")
		self.assertIn(MODIFIER_SEP, name)

	def test_kot_no_arabic_is_byte_for_byte_noop(self):
		name = self._kot_item_name("T-BILING-3", ITEM_EN, "Latte")
		self.assertEqual(name, "Latte")  # EN-only, no separator, no trailing space

	def test_kot_fold_is_per_item_in_batch(self):
		# one AR item + one EN item in the same send -> each folded correctly
		res = kot_send(
			table_label="T-BILING-4",
			items=[
				{"item_code": ITEM_AR, "item_name": "Latte", "qty": 1, "notes": ""},
				{"item_code": ITEM_EN, "item_name": "Water", "qty": 1, "notes": ""},
			],
			pos_profile=self.profile,
		)
		kot = frappe.get_doc("KOT Ticket", res["kot"])
		names = {i.item_code: i.item_name for i in kot.items}
		self.assertEqual(names[ITEM_AR], f"Latte{MODIFIER_SEP}{ARABIC}")
		self.assertEqual(names[ITEM_EN], "Water")
