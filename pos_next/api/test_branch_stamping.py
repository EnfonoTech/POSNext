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
