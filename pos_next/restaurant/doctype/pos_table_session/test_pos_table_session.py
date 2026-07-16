# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api.restaurant import (
	get_session,
	kot_active,
	kot_complete,
	kot_item_ready,
	session_add_item,
	session_cancel,
	session_send_kitchen,
	session_set_qty,
)


class TestPOSTableSession(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("POS Table", "T-TEST-1"):
			frappe.get_doc(
				{"doctype": "POS Table", "table_name": "T-TEST-1", "seats": 4, "area": "Test"}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", "_Test Resto Item"):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "_Test Resto Item",
					"item_name": "_Test Resto Item",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name")
					or "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"standard_rate": 7,
				}
			).insert(ignore_permissions=True)

	def tearDown(self):
		# close any session left open on the test table
		for name in frappe.get_all(
			"POS Table Session", filters={"table": "T-TEST-1", "status": "Open"}, pluck="name"
		):
			frappe.db.set_value("POS Table Session", name, "status", "Cancelled", update_modified=False)
		for name in frappe.get_all("KOT Ticket", filters={"status": "Open"}, pluck="name"):
			frappe.db.set_value("KOT Ticket", name, "status", "Cancelled", update_modified=False)

	def _open_session(self):
		return get_session("T-TEST-1", create=1)

	def test_open_session_is_reused(self):
		s1 = self._open_session()
		s2 = self._open_session()
		self.assertEqual(s1["name"], s2["name"])

	def test_add_item_resolves_rate_server_side(self):
		s = self._open_session()
		out = session_add_item(s["name"], "_Test Resto Item", qty=2)
		self.assertEqual(len(out["items"]), 1)
		line = out["items"][0]
		self.assertEqual(flt(line["rate"]), 7)
		self.assertEqual(flt(line["amount"]), 14)
		self.assertEqual(flt(out["grand_total"]), 14)

	def test_same_item_merges_into_unsent_line(self):
		s = self._open_session()
		session_add_item(s["name"], "_Test Resto Item", qty=1)
		out = session_add_item(s["name"], "_Test Resto Item", qty=2)
		self.assertEqual(len(out["items"]), 1)
		self.assertEqual(flt(out["items"][0]["qty"]), 3)

	def test_send_kitchen_locks_lines_and_reorder_makes_new_line(self):
		s = self._open_session()
		session_add_item(s["name"], "_Test Resto Item", qty=1)
		res = session_send_kitchen(s["name"])
		self.assertFalse(res["already"])
		self.assertTrue(res["kot"])
		sent_line = res["session"]["items"][0]
		self.assertEqual(sent_line["sent_to_kitchen"], 1)
		# sent line cannot be edited
		with self.assertRaises(frappe.ValidationError):
			session_set_qty(s["name"], sent_line["row"], 5)
		# re-order creates a fresh unsent line, not a merge into the sent one
		out = session_add_item(s["name"], "_Test Resto Item", qty=1)
		self.assertEqual(len(out["items"]), 2)
		# second send is not "already" — it fires the new line
		res2 = session_send_kitchen(s["name"])
		self.assertFalse(res2["already"])
		# and a third send with nothing pending is a no-op
		res3 = session_send_kitchen(s["name"])
		self.assertTrue(res3["already"])

	def test_kot_item_ready_autocompletes_ticket(self):
		s = self._open_session()
		session_add_item(s["name"], "_Test Resto Item", qty=1)
		res = session_send_kitchen(s["name"])
		kot = res["kot"]
		active = [k for k in kot_active() if k["name"] == kot]
		self.assertEqual(len(active), 1)
		row = active[0]["items"][0]["row"]
		out = kot_item_ready(kot, row, ready=1)
		self.assertEqual(out["status"], "Completed")

	def test_kot_complete_marks_all_ready(self):
		s = self._open_session()
		session_add_item(s["name"], "_Test Resto Item", qty=1)
		res = session_send_kitchen(s["name"])
		out = kot_complete(res["kot"])
		self.assertEqual(out["status"], "Completed")
		doc = frappe.get_doc("KOT Ticket", res["kot"])
		self.assertTrue(all(i.status == "Ready" for i in doc.items))

	def test_cancel_session(self):
		s = self._open_session()
		out = session_cancel(s["name"])
		self.assertEqual(out["status"], "Cancelled")
		# table is free again — a new open creates a fresh session
		s2 = self._open_session()
		self.assertNotEqual(s["name"], s2["name"])
