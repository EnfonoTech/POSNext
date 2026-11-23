# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The nightly promotion cleanup must work on ERPNext v15's Promotional Scheme.

v15 has separate `selling` / `buying` checkboxes and no `selling_or_buying`
column, so a query naming that column failed every night with
OperationalError 1054 and never disabled anything.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from pos_next.tasks import cleanup_expired_promotions as task


class TestDisableExpiredPromotionalSchemes(FrappeTestCase):
	def setUp(self):
		self.company = frappe.db.get_value("Company", {}, "name")
		self.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not (self.company and self.item_group):
			self.skipTest("needs a Company and a leaf Item Group")
		# The task commits; keep the test inside FrappeTestCase's rollback.
		commit = patch.object(task.frappe.db, "commit")
		commit.start()
		self.addCleanup(commit.stop)

	def _scheme(self, valid_upto):
		return frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"name": f"_Test POS cleanup {valid_upto}",
				"company": self.company,
				"apply_on": "Item Group",
				"item_groups": [{"item_group": self.item_group}],
				"selling": 1,
				"valid_from": add_days(nowdate(), -30),
				"valid_upto": valid_upto,
				"price_discount_slabs": [
					{"rule_description": "5% off", "min_qty": 1, "discount_percentage": 5}
				],
			}
		).insert(ignore_permissions=True)

	def test_expired_scheme_is_disabled_and_job_reports_success(self):
		expired = self._scheme(add_days(nowdate(), -1))
		current = self._scheme(add_days(nowdate(), 10))

		result = task.disable_expired_promotional_schemes()

		self.assertTrue(result["success"], result)
		self.assertGreaterEqual(result["disabled_count"], 1)
		self.assertEqual(frappe.db.get_value("Promotional Scheme", expired.name, "disable"), 1)
		self.assertEqual(frappe.db.get_value("Promotional Scheme", current.name, "disable"), 0)

	def test_no_error_log_when_nothing_expired(self):
		before = frappe.db.count("Error Log", {"method": "Disable Expired Promotional Schemes Error"})

		result = task.disable_expired_promotional_schemes()

		self.assertTrue(result["success"], result)
		after = frappe.db.count("Error Log", {"method": "Disable Expired Promotional Schemes Error"})
		self.assertEqual(before, after)
