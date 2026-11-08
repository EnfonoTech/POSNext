"""pos_next.role_permissions: POS role rights never hide the standard roles' rights.

Regression: the old Custom DocPerm fixture left one bare POS row per DocType, so Frappe ignored the standard
DocPerm rows (Accounts User / Manager ...) and Journal Entry became read-only for everybody (demo.numobooks.co,
2026-11-08)."""

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.role_permissions import GRANTS, POS_ROLES, ensure_role_permissions


def _rows(doctype, table="Custom DocPerm"):
	return {(r.role, r.permlevel, r.if_owner) for r in frappe.get_all(table, filters={"parent": doctype}, fields=["role", "permlevel", "if_owner"])}


def _row(doctype, role):
	return frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}, "*", as_dict=True)


def _reset(doctype, *rows):
	"""Replace the DocType's Custom DocPerm with `rows` (role, {flag: 1}), like a site would have them."""
	frappe.db.delete("Custom DocPerm", {"parent": doctype})
	for role, flags in rows:
		frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType", "parentfield": "permissions", "role": role, "permlevel": 0, **flags}).insert(ignore_permissions=True)


class TestRolePermissions(FrappeTestCase):
	def test_doctype_wiped_by_the_old_fixture_gets_its_standard_rows_back(self):
		_reset("Journal Entry", ("Nexus POS Manager", {"read": 1}))  # what the fixture left on demo
		ensure_role_permissions(quiet=True)
		self.assertTrue(_rows("Journal Entry", "DocPerm") <= _rows("Journal Entry"))
		std = frappe.db.get_value("DocPerm", {"parent": "Journal Entry", "role": "Accounts User", "permlevel": 0}, ["write", "create", "submit"], as_dict=True)
		got = _row("Journal Entry", "Accounts User")
		self.assertEqual((got.write, got.create, got.submit), (std.write, std.create, std.submit))
		pos = _row("Journal Entry", "Nexus POS Manager")
		for f in GRANTS[("Journal Entry", "Nexus POS Manager")]:
			self.assertEqual(pos[f], 1, f)
		self.assertEqual(pos.write, 0)

	def test_doctype_without_custom_rows_copies_the_standard_rows_before_the_grant(self):
		_reset("Territory")
		ensure_role_permissions(quiet=True)
		self.assertTrue(_rows("Territory", "DocPerm") <= _rows("Territory"))
		self.assertTrue(_row("Territory", "POSNext Cashier").read)

	def test_a_site_customisation_is_respected(self):
		_reset("Territory", ("Sales Manager", {"read": 1, "write": 1}))  # set on purpose by the site
		ensure_role_permissions(quiet=True)
		self.assertEqual({r for r, _l, _o in _rows("Territory")}, {"Sales Manager", "POSNext Cashier"})

	def test_flags_are_only_switched_on(self):
		_reset("Territory", ("POSNext Cashier", {"read": 1, "delete": 1}))
		ensure_role_permissions(quiet=True)
		row = _row("Territory", "POSNext Cashier")
		self.assertEqual((row.read, row.export, row.delete), (1, 1, 1))

	def test_second_run_changes_nothing(self):
		ensure_role_permissions(quiet=True)
		before = {dt: _rows(dt) for dt, _r in GRANTS}
		self.assertEqual(ensure_role_permissions(quiet=True), {"restored": [], "granted": []})
		self.assertEqual({dt: _rows(dt) for dt, _r in GRANTS}, before)

	def test_missing_roles_are_created(self):
		self.assertTrue(all(frappe.db.exists("Role", r) for r in POS_ROLES))

	def test_custom_docperm_is_not_a_fixture_any_more(self):
		app = Path(frappe.get_app_path("pos_next"))
		self.assertFalse((app / "fixtures" / "custom_docperm.json").exists())
		self.assertNotIn("Custom DocPerm", [f.get("dt") if isinstance(f, dict) else f for f in frappe.get_hooks("fixtures", app_name="pos_next")])
