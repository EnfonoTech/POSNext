# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class POSComplimentaryOrder(Document):
	def validate(self):
		# Keep the retail value in sync for reporting (free giveaway cost visibility).
		self.total_value = sum(flt(r.amount) for r in (self.items or []))

	def on_update(self):
		# Handle approval decisions made via approve_complimentary_order OR a desk edit
		# of `status`. Only approver roles may move a comp to a decision (belt-and-braces
		# over the doctype write perm); a rejection returns the stock issued at creation.
		prev = self.get_doc_before_save()
		if not prev or prev.status == self.status:
			return
		if self.status in ("Approved", "Rejected"):
			from pos_next.api.restaurant import _comp_stock_return, _guard_comp_approver

			_guard_comp_approver()
			self.db_set("approved_by", frappe.session.user, update_modified=False)
			self.db_set("approved_on", now_datetime(), update_modified=False)
			if self.status == "Rejected":
				# Comp not authorised -> return the stock issued at order time.
				_comp_stock_return(self.name)
