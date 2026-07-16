# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt


class POSTableSession(Document):
	def validate(self):
		total = 0.0
		for item in self.items:
			item.amount = flt(item.qty) * flt(item.rate)
			total += item.amount
		self.grand_total = flt(total)
