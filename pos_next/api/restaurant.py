# Copyright (c) 2026, EnfonoTech and contributors
# For license information, please see license.txt

"""
Restaurant mode API — tables, table sessions (tabs) and KOT (kitchen) tickets.

Design (ported from the Kaapqah restaurant spec, generalised for POSNext):
- A POS Table Session is the open "tab" for one table. One Open session per
  table, enforced by always reusing the existing Open row before inserting.
- Line rates are ALWAYS resolved server-side (POS Profile price list first) —
  the client never sets a trusted price.
- "Send to Kitchen" fires a KOT Ticket for the session's unsent lines only;
  sent lines are locked (already cooking) and are never re-fired or mutated.
- Billing stays on the existing POSNext invoice path (update_invoice /
  submit_invoice, Sales Invoice is_pos=1). settle_session() only links the
  submitted invoice onto the session, idempotently, under a row lock.
- Every mutation publishes a realtime event so the Tables view and the
  Kitchen Display stay live on all devices without polling.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

TABLE_EVENT = "posnext_table_update"
KOT_EVENT = "posnext_kot_update"


def _publish(event, payload):
	"""Broadcast a realtime event to all connected POS / KDS clients.

	after_commit so a rolled-back transaction never emits a ghost event.
	"""
	try:
		frappe.publish_realtime(event, payload, after_commit=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "restaurant realtime publish failed: " + event)


def _resolve_rate(item_code, pos_profile=None):
	"""Server-side price resolution: POS Profile's selling price list first,
	then any selling Item Price, then Item.standard_rate. Throws on disabled
	items and unpriced items — never silently bills 0."""
	if cint(frappe.db.get_value("Item", item_code, "disabled")):
		frappe.throw(_("Item {0} is disabled").format(item_code))

	rate = None
	if pos_profile:
		price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
		if price_list:
			rate = frappe.db.get_value(
				"Item Price",
				{"item_code": item_code, "price_list": price_list, "selling": 1},
				"price_list_rate",
			)
	if rate is None:
		rate = frappe.db.get_value("Item Price", {"item_code": item_code, "selling": 1}, "price_list_rate")
	if rate is None:
		rate = frappe.db.get_value("Item", item_code, "standard_rate")

	rate = flt(rate)
	if rate <= 0:
		frappe.throw(_("No price configured for item {0}").format(item_code))
	return rate


def _session_dict(doc):
	"""Serialize a POS Table Session for the POS frontend."""
	return {
		"name": doc.name,
		"table": doc.table,
		"table_label": doc.table_label or doc.table,
		"status": doc.status,
		"customer": doc.customer,
		"customer_name": doc.customer_name,
		"pos_profile": doc.pos_profile,
		"grand_total": flt(doc.grand_total),
		"opened_at": str(doc.opened_at or doc.creation),
		"sales_invoice": doc.sales_invoice,
		"items": [
			{
				"row": it.name,
				"item_code": it.item_code,
				"item_name": it.item_name,
				"qty": flt(it.qty),
				"rate": flt(it.rate),
				"amount": flt(it.amount),
				"notes": it.notes or "",
				"sent_to_kitchen": cint(it.sent_to_kitchen),
				"source": it.source,
				"kot": it.kot,
			}
			for it in doc.items
		],
	}


def _session_add_line(sess, item_code, item_name, qty, rate, notes="", source="Counter"):
	"""Add qty to an existing UNSENT line of the same item+note, else append a
	new line. Sent lines are never mutated (already cooking) — a re-order of a
	sent item becomes a fresh unsent line, so Send to Kitchen never re-fires
	cooked items."""
	for it in sess.items:
		if (
			it.item_code == item_code
			and not cint(it.sent_to_kitchen)
			and (it.notes or "") == (notes or "")
		):
			it.qty = flt(it.qty) + flt(qty)
			return
	sess.append(
		"items",
		{
			"item_code": item_code,
			"item_name": item_name,
			"qty": flt(qty),
			"rate": flt(rate),
			"amount": flt(rate) * flt(qty),
			"notes": notes or "",
			"sent_to_kitchen": 0,
			"source": source,
		},
	)


def _get_open_session(table, create=False, customer=None, customer_name=None, pos_profile=None):
	"""The single Open session for a table (create if asked)."""
	name = frappe.db.get_value("POS Table Session", {"table": table, "status": "Open"}, "name")
	if name:
		return frappe.get_doc("POS Table Session", name)
	if not create:
		return None
	if not frappe.db.exists("POS Table", table):
		frappe.throw(_("Table {0} not found").format(table))
	doc = frappe.get_doc(
		{
			"doctype": "POS Table Session",
			"table": table,
			"status": "Open",
			"customer": customer,
			"customer_name": customer_name,
			"pos_profile": pos_profile,
			"opened_at": now_datetime(),
			"items": [],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


# ─────────────────────────────────────────────
#  Tables (floor view)
# ─────────────────────────────────────────────


@frappe.whitelist()
def get_tables(pos_profile=None):
	"""Active tables with their open-session summary — the floor map."""
	filters = {"is_active": 1}
	if pos_profile:
		# Tables scoped to this profile OR unscoped (shared floor)
		filters["pos_profile"] = ["in", [pos_profile, "", None]]
	tables = frappe.get_all(
		"POS Table",
		filters=filters,
		fields=["name", "table_name", "seats", "area", "pos_profile"],
		order_by="area asc, table_name asc",
	)
	open_sessions = frappe.get_all(
		"POS Table Session",
		filters={"status": "Open"},
		fields=["name", "table", "customer_name", "grand_total", "opened_at"],
	)
	by_table = {s.table: s for s in open_sessions}
	for t in tables:
		s = by_table.get(t.name)
		t["session"] = (
			{
				"name": s.name,
				"customer_name": s.customer_name,
				"grand_total": flt(s.grand_total),
				"opened_at": str(s.opened_at),
			}
			if s
			else None
		)
		t["occupied"] = bool(s)
	return tables


# ─────────────────────────────────────────────
#  Table sessions (tabs)
# ─────────────────────────────────────────────


@frappe.whitelist()
def get_session(table, create=0, pos_profile=None):
	"""The open session for one table (optionally create an empty one)."""
	sess = _get_open_session(table, create=cint(create), pos_profile=pos_profile)
	if sess and cint(create):
		frappe.db.commit()
		_publish(TABLE_EVENT, {"table": table, "session": sess.name, "action": "open"})
	return _session_dict(sess) if sess else None


@frappe.whitelist()
def session_active(pos_profile=None):
	"""All Open table sessions with items — the POS Tables view."""
	filters = {"status": "Open"}
	if pos_profile:
		filters["pos_profile"] = pos_profile
	names = frappe.get_all("POS Table Session", filters=filters, order_by="opened_at asc", pluck="name")
	return [_session_dict(frappe.get_doc("POS Table Session", n)) for n in names]


@frappe.whitelist()
def session_add_item(session, item_code, qty=1, notes=""):
	"""Cashier adds an item to an open table session. Rate resolved server-side."""
	doc = frappe.get_doc("POS Table Session", session)
	if doc.status != "Open":
		frappe.throw(_("Table session is not open"))
	rate = _resolve_rate(item_code, doc.pos_profile)
	item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
	_session_add_line(doc, item_code, item_name, flt(qty) or 1, rate, notes=cstr(notes))
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(TABLE_EVENT, {"table": doc.table, "session": doc.name, "action": "items"})
	return _session_dict(doc)


@frappe.whitelist()
def session_set_qty(session, row, qty):
	"""Change qty of an unsent line (qty<=0 removes it). Sent lines are locked."""
	doc = frappe.get_doc("POS Table Session", session)
	if doc.status != "Open":
		frappe.throw(_("Table session is not open"))
	q, keep = flt(qty), []
	for it in doc.items:
		if it.name == row:
			if cint(it.sent_to_kitchen):
				frappe.throw(_("Cannot change an item already sent to the kitchen"))
			if q <= 0:
				continue  # drop the line
			it.qty = q
		keep.append(it)
	doc.set("items", keep)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(TABLE_EVENT, {"table": doc.table, "session": doc.name, "action": "items"})
	return _session_dict(doc)


@frappe.whitelist()
def session_send_kitchen(session):
	"""Fire a KOT for the session's unsent items, then mark them sent + link the KOT."""
	doc = frappe.get_doc("POS Table Session", session)
	if doc.status != "Open":
		frappe.throw(_("Table session is not open"))
	pending = [it for it in doc.items if not cint(it.sent_to_kitchen) and flt(it.qty) > 0]
	if not pending:
		return {"session": _session_dict(doc), "kot": None, "already": True}
	kot_items = [
		{
			"item_code": it.item_code,
			"item_name": it.item_name,
			"qty": cint(it.qty) or 1,
			"notes": it.notes or "",
		}
		for it in pending
	]
	res = kot_send(
		table_label=doc.table_label or doc.table,
		items=kot_items,
		pos_profile=doc.pos_profile,
		customer_name=doc.customer_name,
		table=doc.table,
		session=doc.name,
	)
	kot = res.get("kot")
	for it in pending:
		it.sent_to_kitchen = 1
		it.kot = kot
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(TABLE_EVENT, {"table": doc.table, "session": doc.name, "action": "sent"})
	return {"session": _session_dict(doc), "kot": kot, "already": False}


@frappe.whitelist()
def session_settle(session, sales_invoice):
	"""Link a SUBMITTED POS Sales Invoice onto the session and mark it Settled.

	Billing itself goes through the standard POSNext invoice path
	(update_invoice/submit_invoice) — this only records the outcome.
	Idempotent under a row lock: a concurrent settle blocks, then sees the
	invoice set and returns already=True — never a double link."""
	locked = frappe.db.get_value(
		"POS Table Session", session, ["status", "sales_invoice"], for_update=True, as_dict=True
	)
	if not locked:
		frappe.throw(_("Table session not found"))
	if locked.sales_invoice:
		return {"session": _session_dict(frappe.get_doc("POS Table Session", session)), "already": True}
	if locked.status != "Open":
		frappe.throw(_("Table session is not open"))

	inv = frappe.db.get_value("Sales Invoice", sales_invoice, ["docstatus", "is_pos"], as_dict=True)
	if not inv:
		frappe.throw(_("Sales Invoice {0} not found").format(sales_invoice))
	if cint(inv.docstatus) != 1:
		frappe.throw(_("Sales Invoice {0} is not submitted").format(sales_invoice))

	doc = frappe.get_doc("POS Table Session", session)
	frappe.db.set_value(
		"POS Table Session",
		session,
		{"sales_invoice": sales_invoice, "status": "Settled", "settled_at": now_datetime()},
		update_modified=False,
	)
	frappe.db.commit()
	_publish(TABLE_EVENT, {"table": doc.table, "session": session, "action": "settled"})
	return {
		"session": _session_dict(frappe.get_doc("POS Table Session", session)),
		"invoice": sales_invoice,
		"already": False,
	}


@frappe.whitelist()
def session_cancel(session):
	"""Void an open table session (no bill). Already-fired KOTs are completed separately."""
	doc = frappe.get_doc("POS Table Session", session)
	if doc.status == "Open":
		doc.status = "Cancelled"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		_publish(TABLE_EVENT, {"table": doc.table, "session": doc.name, "action": "cancelled"})
	return {"session": _session_dict(doc), "status": doc.status}


# ─────────────────────────────────────────────
#  Kitchen (KOT) — server-backed, multi-device
# ─────────────────────────────────────────────


@frappe.whitelist()
def kot_send(table_label, items, pos_profile=None, customer_name=None, table=None, session=None):
	"""Create a KOT ticket (or append to the table's open ticket).

	items = JSON list of {item_code, item_name, qty, notes}."""
	if isinstance(items, str):
		items = json.loads(items)
	items = [it for it in items if cint(it.get("qty")) > 0]
	if not items:
		frappe.throw(_("No items to send to kitchen"))

	open_name = frappe.db.get_value(
		"KOT Ticket",
		{"table_label": table_label, "status": "Open"},
		"name",
		order_by="creation desc",
	)
	if open_name:
		# Re-fetch the open ticket row under a row lock so concurrent sends to
		# the same table serialise — the second send appends after the first
		# commits instead of silently clobbering it.
		frappe.db.get_value("KOT Ticket", open_name, "name", for_update=True)
		doc = frappe.get_doc("KOT Ticket", open_name)
	else:
		doc = frappe.new_doc("KOT Ticket")
		doc.table_label = table_label
		doc.table = table
		doc.session = session
		doc.pos_profile = pos_profile
		doc.customer_name = customer_name
		doc.status = "Open"
		doc.ordered_at = now_datetime()

	for it in items:
		doc.append(
			"items",
			{
				"item_code": it.get("item_code"),
				"item_name": cstr(it.get("item_name") or it.get("item_code")),
				"qty": cint(it.get("qty")) or 1,
				"notes": it.get("notes") or "",
				"status": "Pending",
			},
		)
	if customer_name and not doc.customer_name:
		doc.customer_name = customer_name
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(KOT_EVENT, {"kot": doc.name, "action": "new"})
	return {"kot": doc.name, "status": doc.status}


@frappe.whitelist()
def kot_active(pos_profile=None):
	"""Open KOT tickets with items — the Kitchen Display feed."""
	filters = {"status": "Open"}
	if pos_profile:
		filters["pos_profile"] = pos_profile
	names = frappe.get_all("KOT Ticket", filters=filters, order_by="creation asc", pluck="name")
	out = []
	for n in names:
		d = frappe.get_doc("KOT Ticket", n)
		out.append(
			{
				"name": d.name,
				"table": d.table,
				"table_label": d.table_label,
				"session": d.session,
				"customer_name": d.customer_name,
				"ordered_at": str(d.ordered_at or d.creation),
				"items": [
					{
						"row": i.name,
						"item_code": i.item_code,
						"item_name": i.item_name,
						"qty": i.qty,
						"notes": i.notes,
						"status": i.status,
					}
					for i in d.items
				],
			}
		)
	return out


@frappe.whitelist()
def kot_item_ready(kot, row, ready=1):
	"""Mark one KOT item Ready/Pending; auto-complete the ticket when all are Ready."""
	doc = frappe.get_doc("KOT Ticket", kot)
	for i in doc.items:
		if i.name == row:
			i.status = "Ready" if cint(ready) else "Pending"
	if doc.items and all(i.status == "Ready" for i in doc.items):
		doc.status = "Completed"
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(KOT_EVENT, {"kot": doc.name, "action": "item", "status": doc.status})
	return {"kot": doc.name, "status": doc.status}


@frappe.whitelist()
def kot_complete(kot):
	"""Mark a whole ticket completed (all items Ready)."""
	doc = frappe.get_doc("KOT Ticket", kot)
	for i in doc.items:
		i.status = "Ready"
	doc.status = "Completed"
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(KOT_EVENT, {"kot": doc.name, "action": "complete", "status": doc.status})
	return {"kot": doc.name, "status": doc.status}
