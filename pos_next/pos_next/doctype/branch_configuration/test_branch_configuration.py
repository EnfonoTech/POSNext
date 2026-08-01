# Copyright (c) 2026, BrainWise and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestBranchConfiguration(FrappeTestCase):
	def test_rejects_group_cost_center(self):
		"""A group cost center must be rejected — postings need a leaf."""
		company = frappe.db.get_value("Company", {}, "name")
		group_cc = frappe.db.get_value("Cost Center", {"company": company, "is_group": 1}, "name")
		if not (company and group_cc):
			self.skipTest("no company/group cost center on this site")
		branch = _ensure_branch("_Test Branch Group CC")
		doc = frappe.get_doc(
			{
				"doctype": "Branch Configuration",
				"branch": branch,
				"company": company,
				"cost_center": group_cc,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_rejects_duplicate_cost_center(self):
		"""The same cost center cannot back two branches."""
		company = frappe.db.get_value("Company", {}, "name")
		leaf_cc = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
		if not (company and leaf_cc):
			self.skipTest("no leaf cost center on this site")

		first = frappe.get_doc(
			{
				"doctype": "Branch Configuration",
				"branch": _ensure_branch("_Test Branch A"),
				"company": company,
				"cost_center": leaf_cc,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Branch Configuration", first.name, force=True))

		second = frappe.get_doc(
			{
				"doctype": "Branch Configuration",
				"branch": _ensure_branch("_Test Branch B"),
				"company": company,
				"cost_center": leaf_cc,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			second.insert(ignore_permissions=True)

	def test_invalid_prefix_rejected(self):
		company = frappe.db.get_value("Company", {}, "name")
		leaf_cc = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
		if not (company and leaf_cc):
			self.skipTest("no leaf cost center on this site")
		doc = frappe.get_doc(
			{
				"doctype": "Branch Configuration",
				"branch": _ensure_branch("_Test Branch Prefix"),
				"company": company,
				"cost_center": leaf_cc,
				"naming_series_prefix": "toolongprefix",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_registers_branch_accounting_dimension(self):
		"""Saving a config must make Branch a usable accounting dimension."""
		from pos_next.pos_next.doctype.branch_configuration.branch_configuration import (
			ensure_branch_dimension,
		)

		ensure_branch_dimension()
		self.assertTrue(frappe.db.exists("Accounting Dimension", "Branch"))


def _ensure_branch(name: str) -> str:
	if not frappe.db.exists("Branch", name):
		frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True)
	return name
