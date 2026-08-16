# Copyright (c) 2026, BrainWise and contributors
# See license.txt

"""Regression guard: every GL row of a POS sale must carry the branch.

This is the bug this feature exists to prevent — cost center only lands on item
rows, so VAT/receivable/cash rows used to fall back to the company default.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestBranchStamping(FrappeTestCase):
	def test_all_gl_entries_carry_branch(self):
		config = frappe.get_all(
			"Branch Configuration",
			filters={"disabled": 0, "pos_profile": ["is", "set"]},
			fields=["name", "branch", "pos_profile", "company", "cost_center"],
			limit=1,
		)
		if not config:
			self.skipTest("no Branch Configuration with a POS Profile on this site")
		cfg = config[0]

		invoice = frappe.get_all(
			"Sales Invoice",
			filters={"docstatus": 1, "pos_profile": cfg.pos_profile, "branch": cfg.branch},
			pluck="name",
			order_by="creation desc",
			limit=1,
		)
		if not invoice:
			self.skipTest("no submitted branch-stamped invoice yet")

		rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": invoice[0], "is_cancelled": 0},
			fields=["account", "branch"],
		)
		self.assertTrue(rows, "invoice produced no GL entries")
		unstamped = [r.account for r in rows if not r.branch]
		self.assertFalse(
			unstamped,
			f"GL rows missing branch (the bug this guards): {unstamped}",
		)

	def test_tax_rows_carry_branch_cost_center(self):
		"""VAT must post to the branch cost centre, not the company default.

		ERPNext fills a tax row's cost center from the company, so without the
		branch hook the VAT GL line lands on e.g. "Main - CO" while the income
		lines sit on the branch. This test pins that regression.
		"""
		config = frappe.get_all(
			"Branch Configuration",
			filters={"disabled": 0, "pos_profile": ["is", "set"], "cost_center": ["is", "set"]},
			fields=["branch", "pos_profile", "cost_center"],
			limit=1,
		)
		if not config:
			self.skipTest("no Branch Configuration with a POS Profile and cost centre")
		cfg = config[0]

		invoice = frappe.get_all(
			"Sales Invoice",
			filters={"docstatus": 1, "pos_profile": cfg.pos_profile, "branch": cfg.branch},
			pluck="name",
			order_by="creation desc",
			limit=1,
		)
		if not invoice:
			self.skipTest("no submitted branch-stamped invoice yet")

		doc = frappe.get_doc("Sales Invoice", invoice[0])
		wrong = [
			(t.account_head, t.cost_center)
			for t in doc.taxes
			if t.cost_center and t.cost_center != cfg.cost_center
		]
		self.assertFalse(wrong, f"tax rows not on the branch cost centre: {wrong}")

		gl_wrong = [
			(r.account, r.cost_center)
			for r in frappe.get_all(
				"GL Entry",
				filters={"voucher_no": doc.name, "is_cancelled": 0},
				fields=["account", "cost_center"],
			)
			if r.cost_center and r.cost_center != cfg.cost_center
		]
		self.assertFalse(gl_wrong, f"GL rows not on the branch cost centre: {gl_wrong}")


class TestBranchNamingSeries(FrappeTestCase):
	"""The series stamped on the invoice must be the one the master registered.

	`BranchConfiguration.ensure_naming_series_option` derives the Sales Invoice
	naming_series option with `series_from_prefix`, which passes a prefix that is
	already a complete series (TCS-SI-.YYYY.-) through untouched. Building the
	series inline here instead used to append a second suffix, producing
	TCS-SI-.YYYY.--.YYYY.- — a series that is not in the option list at all.
	"""

	def _stamp(self, prefix):
		from unittest.mock import patch

		from pos_next.api import branch as branch_api

		config = frappe._dict(
			{
				"branch": "Test Branch",
				"cost_center": None,
				"warehouse": None,
				"naming_series_prefix": prefix,
			}
		)
		doc = frappe._dict({"naming_series": None, "branch": None, "pos_profile": "Test POS"})
		doc.meta = frappe._dict({"get_field": lambda fieldname: object()})

		with patch.object(branch_api, "_branches_configured", return_value=True), patch.object(
			branch_api, "get_branch_config", return_value=config
		):
			branch_api.apply_branch_defaults(doc)
		return doc.naming_series

	def test_bare_prefix_gets_year_suffix(self):
		self.assertEqual(self._stamp("COL"), "COL-.YYYY.-")

	def test_complete_series_is_not_double_suffixed(self):
		self.assertEqual(self._stamp("TCS-SI-.YYYY.-"), "TCS-SI-.YYYY.-")

	def test_stamped_series_matches_the_registered_option(self):
		from pos_next.pos_next.doctype.branch_configuration.branch_configuration import (
			series_from_prefix,
		)

		for prefix in ("COL", "RAS", "JAF", "TAR", "MAZ", "TCS-SI-.YYYY.-"):
			self.assertEqual(self._stamp(prefix), series_from_prefix(prefix), prefix)
