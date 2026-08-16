# Copyright (c) 2026, BrainWise and contributors
# See license.txt

from frappe import _
from frappe.tests.utils import FrappeTestCase

from pos_next.pos_next.report.pos_payment_exceptions.pos_payment_exceptions import _classify


class TestPOSPaymentExceptions(FrappeTestCase):
	"""The classifier carries the whole judgement of this report, so it is
	tested directly rather than through a fixture-heavy end-to-end run."""

	def test_reconciled_bill_is_not_an_exception(self):
		# Billed 22, tendered 22, no change: nothing to report.
		self.assertIsNone(_classify(outstanding=0.0, difference=0.0))

	def test_cash_bill_with_change_is_not_an_exception(self):
		# Billed 22, tendered 50, change 28 -> kept 22. Outstanding nets to zero.
		self.assertIsNone(_classify(outstanding=0.0, difference=0.0))

	def test_card_overpayment_is_flagged(self):
		# Billed 22, tendered 44 on a Bank mode: no change computed, outstanding -22.
		self.assertEqual(_classify(outstanding=-22.0, difference=22.0), _("Overpaid"))

	def test_short_payment_is_flagged(self):
		self.assertEqual(_classify(outstanding=5.0, difference=-5.0), _("Short paid"))

	def test_tender_mismatch_without_outstanding_is_flagged(self):
		# Ledger nets out but the tender line still disagrees with the bill.
		self.assertEqual(_classify(outstanding=0.0, difference=12.0), _("Tender mismatch"))

	def test_rounding_noise_is_not_an_exception(self):
		# Half a halala either way must not raise an exception row.
		self.assertIsNone(_classify(outstanding=0.004, difference=-0.004))
