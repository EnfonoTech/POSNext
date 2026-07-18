# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

"""
TDD suite (pre-implementation) — Feature 2: Table transfer.

Written BEFORE the implementation exists — the module-level import of
`transfer_table` raises ImportError until implemented, so the whole file
reports RED now and PASSES once the spec in .pipeline/spec.md is implemented.

Encodes spec §"Implementation Steps 5" + "Edge Cases (Feature 2)" +
"Test Plan (transfer_table …)":
  - from_table != to_table; both exist + is_active.
  - Row-lock the source Open session; throw "source not open" if none.
  - Re-check target free under the lock; throw "target occupied" if it has an
    Open POS Table Session.
  - Move the SAME Open session (table + table_label) to the target; never a new
    session row.
  - Relink every Open KOT Ticket {table: from, status: Open} -> to_table
    (+ table_label). Completed/Cancelled KOTs are historical and left alone.
  - Concurrency: a second transfer of the same source (now moved) sees the
    source no longer Open -> throws (no double move).
  - Returns {"session": <name>, "to_table": to_table}.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

# ── RED trigger: transfer_table does not exist yet ─────────────────────
from pos_next.api.restaurant import (
	get_session,
	session_add_item,
	session_send_kitchen,
	transfer_table,
)

SRC = "T-XFER-SRC"
DST = "T-XFER-DST"
DST2 = "T-XFER-DST2"
INACTIVE = "T-XFER-INACTIVE"
ITEM = "_XFER Item"


def _ensure_table(name, is_active=1):
	if not frappe.db.exists("POS Table", name):
		frappe.get_doc(
			{"doctype": "POS Table", "table_name": name, "seats": 4, "area": "Xfer", "is_active": is_active}
		).insert(ignore_permissions=True)
	else:
		frappe.db.set_value("POS Table", name, "is_active", is_active)


def _label(table):
	return frappe.db.get_value("POS Table", table, "table_name")


class TestTransferTable(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_table(SRC)
		_ensure_table(DST)
		_ensure_table(DST2)
		_ensure_table(INACTIVE, is_active=0)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name")
					or "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
					"standard_rate": 7,
				}
			).insert(ignore_permissions=True)

	def tearDown(self):
		for t in (SRC, DST, DST2):
			for name in frappe.get_all(
				"POS Table Session", filters={"table": t, "status": "Open"}, pluck="name"
			):
				frappe.db.set_value("POS Table Session", name, "status", "Cancelled", update_modified=False)
		for name in frappe.get_all("KOT Ticket", filters={"status": "Open"}, pluck="name"):
			frappe.db.set_value("KOT Ticket", name, "status", "Cancelled", update_modified=False)
		frappe.db.commit()

	def _open_with_item(self, table):
		s = get_session(table, create=1)
		session_add_item(s["name"], ITEM, qty=1)
		return frappe.db.get_value("POS Table Session", {"table": table, "status": "Open"}, "name")

	# ── success ────────────────────────────────────────────────────────
	def test_moves_same_open_session_to_target(self):
		src_session = self._open_with_item(SRC)
		res = transfer_table(SRC, DST)
		# same session row, now bound to the target table
		self.assertEqual(res["session"], src_session)
		self.assertEqual(res["to_table"], DST)
		self.assertEqual(frappe.db.get_value("POS Table Session", src_session, "table"), DST)
		self.assertEqual(frappe.db.get_value("POS Table Session", src_session, "table_label"), _label(DST))
		self.assertEqual(frappe.db.get_value("POS Table Session", src_session, "status"), "Open")
		# source no longer has an Open session; no NEW session created
		self.assertFalse(
			frappe.db.exists("POS Table Session", {"table": SRC, "status": "Open"})
		)

	def test_relinks_open_kot_tickets(self):
		src_session = self._open_with_item(SRC)
		sk = session_send_kitchen(src_session)
		kot = sk["kot"]
		self.assertEqual(frappe.db.get_value("KOT Ticket", kot, "table"), SRC)
		transfer_table(SRC, DST)
		self.assertEqual(frappe.db.get_value("KOT Ticket", kot, "table"), DST)
		self.assertEqual(frappe.db.get_value("KOT Ticket", kot, "table_label"), _label(DST))
		self.assertEqual(frappe.db.get_value("KOT Ticket", kot, "status"), "Open")

	def test_completed_kot_is_left_alone(self):
		from pos_next.api.restaurant import kot_complete

		src_session = self._open_with_item(SRC)
		sk = session_send_kitchen(src_session)
		kot = sk["kot"]
		kot_complete(kot)  # historical now
		transfer_table(SRC, DST)
		# a completed ticket is history — it must NOT be relinked
		self.assertEqual(frappe.db.get_value("KOT Ticket", kot, "table"), SRC)
		self.assertEqual(frappe.db.get_value("KOT Ticket", kot, "status"), "Completed")

	# ── guards ─────────────────────────────────────────────────────────
	def test_source_without_open_session_throws(self):
		# SRC has no Open session -> nothing to move
		with self.assertRaises(frappe.ValidationError):
			transfer_table(SRC, DST)

	def test_target_occupied_throws(self):
		self._open_with_item(SRC)
		self._open_with_item(DST)  # target already has an Open session
		with self.assertRaises(frappe.ValidationError):
			transfer_table(SRC, DST)
		# source session untouched
		self.assertTrue(frappe.db.exists("POS Table Session", {"table": SRC, "status": "Open"}))

	def test_same_table_throws(self):
		self._open_with_item(SRC)
		with self.assertRaises(frappe.ValidationError):
			transfer_table(SRC, SRC)

	def test_nonexistent_target_throws(self):
		self._open_with_item(SRC)
		with self.assertRaises(frappe.ValidationError):
			transfer_table(SRC, "T-XFER-NOPE")

	def test_inactive_target_throws(self):
		self._open_with_item(SRC)
		with self.assertRaises(frappe.ValidationError):
			transfer_table(SRC, INACTIVE)

	# ── concurrency (no double move) ────────────────────────────────────
	def test_second_transfer_of_moved_source_throws(self):
		# Encodes the for_update outcome sequentially: once the session has moved,
		# the source is no longer Open, so a second transfer sees "source not open"
		# and cannot move it again into a different target.
		self._open_with_item(SRC)
		transfer_table(SRC, DST)
		with self.assertRaises(frappe.ValidationError):
			transfer_table(SRC, DST2)
		# DST2 stays free; the single session lives on DST only
		self.assertFalse(frappe.db.exists("POS Table Session", {"table": DST2, "status": "Open"}))
		self.assertTrue(frappe.db.exists("POS Table Session", {"table": DST, "status": "Open"}))

	def test_two_sources_cannot_both_land_on_one_free_target(self):
		# Two DIFFERENT open sources transferring into the SAME free target. The source
		# for_update lock is per-source, so the two never contend on it; correctness rests on
		# serialising on the target's POS Table row + a locking occupied re-check. Encoded
		# sequentially (like test_second_transfer_of_moved_source_throws above): the winner
		# lands on the target, the loser then reads the latest committed state, sees the target
		# occupied and throws -> exactly one Open session ever lives on the target.
		self._open_with_item(SRC)
		src_b = self._open_with_item(DST2)
		transfer_table(SRC, DST)  # winner
		with self.assertRaises(frappe.ValidationError):
			transfer_table(DST2, DST)  # loser: target now occupied
		# exactly one Open session on the target
		self.assertEqual(frappe.db.count("POS Table Session", {"table": DST, "status": "Open"}), 1)
		# the loser's session is untouched, still on its own table
		self.assertEqual(frappe.db.get_value("POS Table Session", src_b, "table"), DST2)
		self.assertTrue(frappe.db.exists("POS Table Session", {"table": DST2, "status": "Open"}))
