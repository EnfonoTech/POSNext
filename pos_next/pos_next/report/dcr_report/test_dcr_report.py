# Copyright (c) 2026, BrainWise and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from pos_next.pos_next.report.dcr_report.dcr_report import execute


class TestDCRReport(FrappeTestCase):
	def test_requires_company_and_dates(self):
		with self.assertRaises(frappe.ValidationError):
			execute({"from_date": nowdate(), "to_date": nowdate()})
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no company on this site")
		with self.assertRaises(frappe.ValidationError):
			execute({"company": company})

	def test_rejects_reversed_date_range(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no company on this site")
		with self.assertRaises(frappe.ValidationError):
			execute({"company": company, "from_date": "2026-12-31", "to_date": "2026-01-01"})

	def test_runs_and_brackets_movement_with_balances(self):
		"""Opening and Closing must bracket the report, whatever the data."""
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no company on this site")
		columns, data = execute(
			{"company": company, "from_date": nowdate(), "to_date": nowdate()}
		)
		self.assertTrue(columns)
		labels = [r["particulars"] for r in data]
		self.assertEqual(labels[0], "Opening Cash Balance")
		self.assertIn("Closing Cash Balance", labels)
		self.assertIn("VAT Collected", labels)
