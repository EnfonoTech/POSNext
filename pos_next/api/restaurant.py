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


# ─────────────────────────────────────────────
#  Menu-item modifiers (Size, Extras, …)
# ─────────────────────────────────────────────

MODIFIER_SEP = " · "


def _resolve_item_modifiers(item_code):
	"""Resolve the modifier groups configured on an Item into a display/pricing
	structure, in configuration (idx) order. Disabled groups and disabled options
	are excluded — they are never priced and never selectable. Cached per-request
	in frappe.flags, keyed by item, so repeated calls in one request hit no DB."""
	cache = frappe.flags.setdefault("_pos_item_modifiers", {})
	if item_code in cache:
		return cache[item_code]

	rows = frappe.get_all(
		"POS Item Modifier",
		filters={"parent": item_code, "parenttype": "Item", "parentfield": "custom_modifier_groups"},
		fields=["modifier_group"],
		order_by="idx asc",
	)
	groups = []
	for row in rows:
		grp = frappe.get_cached_doc("POS Modifier Group", row.modifier_group)
		if cint(grp.disabled):
			continue
		options = [
			{
				"label": o.option_label,
				"price_delta": flt(o.price_delta),
				"is_default": cint(o.is_default),
			}
			for o in grp.options
			if not cint(o.disabled)
		]
		groups.append(
			{
				"group_name": grp.group_name,
				"selection_type": grp.selection_type,
				"is_required": cint(grp.is_required),
				"min": cint(grp.min_select),
				"max": cint(grp.max_select),
				"options": options,
			}
		)
	cache[item_code] = groups
	return groups


def _parse_modifier_selection(modifiers):
	"""Normalise the client selection to a dict {group_name: label | [labels]}.
	Accepts a dict, a JSON string, or a falsy value (-> empty selection)."""
	if not modifiers:
		return {}
	if isinstance(modifiers, str):
		try:
			modifiers = json.loads(modifiers)
		except (ValueError, TypeError):
			frappe.throw(_("Invalid modifier selection"))
	if not isinstance(modifiers, dict):
		frappe.throw(_("Invalid modifier selection"))
	return modifiers


def _selected_labels(value):
	"""One selection value -> a clean list of chosen labels."""
	if value is None or value == "":
		return []
	if isinstance(value, (list, tuple)):
		return [cstr(v) for v in value if cstr(v) != ""]
	return [cstr(value)]


def _price_with_modifiers(item_code, base_rate, modifiers):
	"""Return (rate, validated_selection, note) for a modifier selection.

	The client sends only the selection (group -> label(s)); every price comes
	from server config. rate = flt(base_rate + sum of selected price_delta).
	Validates group/option membership, single-select, required, min/max. The note
	lists the chosen options joined by ' · ' in configuration order. An empty
	selection with no required groups returns the base rate and an empty note."""
	selection = _parse_modifier_selection(modifiers)
	groups = _resolve_item_modifiers(item_code)
	by_name = {g["group_name"]: g for g in groups}

	# Reject any group the client sent that is not offered by this item (also
	# catches disabled/unknown groups, which are absent from the resolved list).
	for key in selection:
		if key not in by_name:
			frappe.throw(_("Modifier group {0} is not available for item {1}").format(key, item_code))

	note_parts = []
	total_delta = 0.0
	validated = {}

	for grp in groups:  # configuration order
		# De-duplicate: the same option sent twice is one distinct pick. len(picks)
		# gates min/max while pricing counts distinct options — keep them consistent
		# so ["MA","MA"] can't falsely satisfy min_select or trip max_select.
		picks = list(dict.fromkeys(_selected_labels(selection.get(grp["group_name"]))))

		if grp["selection_type"] == "Single" and len(picks) > 1:
			frappe.throw(_("Only one option may be selected for {0}").format(grp["group_name"]))
		if grp["is_required"] and not picks:
			frappe.throw(_("Please select an option for {0}").format(grp["group_name"]))
		if not picks:
			continue  # optional group left blank -> not engaged

		if grp["min"] and len(picks) < grp["min"]:
			frappe.throw(_("Select at least {0} option(s) for {1}").format(grp["min"], grp["group_name"]))
		if grp["max"] and len(picks) > grp["max"]:
			frappe.throw(_("Select at most {0} option(s) for {1}").format(grp["max"], grp["group_name"]))

		valid_labels = {o["label"] for o in grp["options"]}
		for label in picks:
			if label not in valid_labels:
				frappe.throw(_("{0} is not a valid option for {1}").format(label, grp["group_name"]))

		# Accumulate in configuration order, not the order the client sent them.
		chosen = []
		for opt in grp["options"]:
			if opt["label"] in picks:
				total_delta += flt(opt["price_delta"])
				note_parts.append(opt["label"])
				chosen.append(opt["label"])
		validated[grp["group_name"]] = chosen

	rate = flt(flt(base_rate) + flt(total_delta))
	note = MODIFIER_SEP.join(note_parts)
	return rate, validated, note


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
def get_item_modifiers(item_code=None):
	"""Resolved modifier groups for the POS menu. One item's groups when
	item_code is given, else the full {item_code: groups} map for every item
	that has any. Staff-only (whitelisted, NOT allow_guest) — do not leak the
	menu/price structure to guests. price_delta is for display only; the line
	rate is always re-resolved server-side at add time."""
	if item_code:
		return _resolve_item_modifiers(item_code)

	parents = frappe.get_all(
		"POS Item Modifier",
		filters={"parenttype": "Item", "parentfield": "custom_modifier_groups"},
		pluck="parent",
	)
	out = {}
	for parent in set(parents):
		groups = _resolve_item_modifiers(parent)
		if groups:
			out[parent] = groups
	return out


@frappe.whitelist()
def get_modifier_selection(item_code, modifiers=None):
	"""Server-authoritative, DELTA-ONLY modifier pricing for the dine-in main cart.

	The main cart owns the base rate (Q2 LOCKED: delta-only) — this endpoint only
	returns the validated modifier contribution so there is never a second base-price
	source of truth. Reuses _price_with_modifiers with base 0, so the returned "rate"
	IS the summed option deltas, and it inherits the full validation (required / min /
	max / single / membership / disabled group+option). Staff-only (whitelisted, NOT
	allow_guest), matching get_item_modifiers.

	Returns {delta, note, validated}. An empty/None selection with no required group
	returns {delta 0, note "", validated {}}."""
	delta, validated, note = _price_with_modifiers(item_code, 0, modifiers)
	return {"delta": flt(delta), "note": note, "validated": validated}


@frappe.whitelist()
def session_add_item(session, item_code, qty=1, notes="", modifiers=None):
	"""Cashier adds an item to an open table session. Rate resolved server-side.

	`modifiers` is the client's group->label(s) selection (dict or JSON string).
	The line rate is base rate + server-side option deltas; the selection summary
	is folded into the line note (so distinct selections form distinct lines and
	flow to the KOT). `modifiers=None` reproduces the un-modified behaviour."""
	doc = frappe.get_doc("POS Table Session", session)
	if doc.status != "Open":
		frappe.throw(_("Table session is not open"))
	base_rate = _resolve_rate(item_code, doc.pos_profile)
	rate, _validated, mod_note = _price_with_modifiers(item_code, base_rate, modifiers)
	line_note = MODIFIER_SEP.join(p for p in [mod_note, cstr(notes)] if p)
	item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
	_session_add_line(doc, item_code, item_name, flt(qty) or 1, rate, notes=line_note)
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

	# Bilingual KOT: the kitchen sees "Latte · لاتيه" on the KDS + printed ticket
	# without any KOT Ticket Item schema change. One batched Item.custom_arabic_name
	# lookup for all lines; a byte-for-byte no-op when the Arabic name is empty.
	codes = [it.get("item_code") for it in items if it.get("item_code")]
	ar_map = {}
	if codes:
		ar_map = {
			r.name: cstr(r.custom_arabic_name or "")
			for r in frappe.get_all(
				"Item", filters={"name": ["in", codes]}, fields=["name", "custom_arabic_name"]
			)
		}

	for it in items:
		name_en = cstr(it.get("item_name") or it.get("item_code"))
		ar = ar_map.get(it.get("item_code"), "")
		doc.append(
			"items",
			{
				"item_code": it.get("item_code"),
				"item_name": f"{name_en}{MODIFIER_SEP}{ar}" if ar else name_en,
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


# ─────────────────────────────────────────────
#  Table transfer (move an open table to a free one)
# ─────────────────────────────────────────────


@frappe.whitelist()
def transfer_table(from_table, to_table):
	"""Move an open table's dine-in binding — its single Open POS Table Session plus
	every Open KOT Ticket — to another free table. Realtime-published so all floor
	devices reconcile.

	Row-locks the source session (mirror session_settle's for_update) so a concurrent
	transfer of the SAME source serialises and can't double-move it. Separately serialises
	on the TARGET's POS Table row and re-checks target-free with a locking read, so two
	transfers from DIFFERENT sources into the same free target can't both win either.
	The same session row moves — no new session is ever created."""
	# Authz gate (Reviewer #3): moving a table's Open session + relinking its KOTs is a
	# floor-state mutation, not a read — require POS Table Session write (System Manager /
	# Sales Manager / Nexus POS Manager / POSNext Cashier hold it) rather than letting any
	# authenticated user reassign tables. Administrator/perm-holders pass; others 403.
	frappe.has_permission("POS Table Session", "write", throw=True)
	if from_table == to_table:
		frappe.throw(_("Source and target tables must be different"))
	for t in (from_table, to_table):
		if not frappe.db.exists("POS Table", t):
			frappe.throw(_("Table {0} not found").format(t))
	if not cint(frappe.db.get_value("POS Table", from_table, "is_active")):
		frappe.throw(_("Table {0} is not active").format(from_table))
	if not cint(frappe.db.get_value("POS Table", to_table, "is_active")):
		frappe.throw(_("Table {0} is not active").format(to_table))

	src = frappe.db.get_value(
		"POS Table Session", {"table": from_table, "status": "Open"}, "name", for_update=True
	)
	if not src:
		frappe.throw(_("Source table {0} has no open session").format(from_table))

	# Serialise every transfer targeting this table on the target's POS Table row before the
	# occupied check. The source for_update above locks only the SOURCE session, so two
	# transfers from DIFFERENT sources into the same free target would otherwise both pass the
	# check and both land on it. The loser blocks here until the winner commits and releases.
	frappe.db.get_value("POS Table", to_table, "name", for_update=True)

	# Locking read so the occupied check reads the LATEST committed state: a plain read would
	# use this request's REPEATABLE READ snapshot (taken before the winner committed) and miss
	# the session the winner just moved onto the target.
	if frappe.db.get_value(
		"POS Table Session", {"table": to_table, "status": "Open"}, "name", for_update=True
	):
		frappe.throw(_("Target table {0} is already occupied").format(to_table))

	to_label = frappe.db.get_value("POS Table", to_table, "table_name")
	frappe.db.set_value("POS Table Session", src, {"table": to_table, "table_label": to_label})

	# Relink every Open KOT ticket for the source; Completed/Cancelled tickets are
	# historical and left on the old table. No parent.save() — KOT Ticket is not
	# submittable, so a direct field write is enough.
	for kot in frappe.get_all(
		"KOT Ticket", filters={"table": from_table, "status": "Open"}, pluck="name"
	):
		frappe.db.set_value("KOT Ticket", kot, {"table": to_table, "table_label": to_label})

	frappe.db.commit()
	_publish(TABLE_EVENT, {"from": from_table, "to": to_table, "action": "transfer"})
	_publish(KOT_EVENT, {"from": from_table, "to": to_table, "action": "transfer"})
	return {"session": src, "to_table": to_table}


# ─────────────────────────────────────────────
#  Complimentary / Void order (stock-affecting, no Sales Invoice)
# ─────────────────────────────────────────────

COMP_APPROVER_ROLES = ("System Manager", "Sales Manager", "Nexus POS Manager")


def _is_comp_approver(user=None):
	"""True if `user` (default: session user) may approve/reject a comp order."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(COMP_APPROVER_ROLES))


def _guard_comp_approver():
	"""Throw PermissionError unless the session user holds an approver role. Backs the
	doctype write perm (POSNext Cashier is create-only) for both the endpoint and any
	desk edit of `status`."""
	if not _is_comp_approver():
		frappe.throw(
			_("You are not permitted to approve complimentary orders"), frappe.PermissionError
		)


def _comp_stock_context(pos_profile):
	"""Resolve (company, warehouse, cost_center) for the comp Material Issue.
	Warehouse = POS Profile.warehouse; cost_center = POS Profile.cost_center falling
	back to Company.cost_center."""
	company = warehouse = cost_center = None
	if pos_profile:
		p = frappe.db.get_value(
			"POS Profile", pos_profile, ["company", "warehouse", "cost_center"], as_dict=True
		)
		if p:
			company, warehouse, cost_center = p.company, p.warehouse, p.cost_center
	if not company:
		company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
			"Company", {"name": ["!=", ""]}, "name"
		)
	if not cost_center and company:
		cost_center = frappe.get_cached_value("Company", company, "cost_center")
	return company, warehouse, cost_center


def _bom_raw_needs(menu_lines):
	"""Aggregate default-BOM raw-material needs for non-stock menu lines
	(list of {item_code, qty}). Returns {raw_item_code: qty} for STOCK raws only.

	A non-stock BOM raw is DROPPED (and logged): a Material Issue rejects a non-stock
	line and Frappe aborts the ENTIRE issue on it, which would silently lose the whole
	(otherwise valid) reversal. Kaapqah kept BOM raws is_stock_item=1 by construction;
	this port restores that invariant explicitly (Reviewer #2). A non-stock item with no
	submitted default BOM contributes nothing (no throw). Mirrors Kaapqah's
	inventory._post_bom_consumption need computation."""
	codes = list({l["item_code"] for l in menu_lines if l.get("item_code")})
	if not codes:
		return {}
	boms = {
		b.item: b.name
		for b in frappe.get_all(
			"BOM",
			filters={"item": ["in", codes], "is_default": 1, "docstatus": 1},
			fields=["item", "name"],
		)
	}
	if not boms:
		return {}
	bom_lines = frappe.get_all(
		"BOM Item", filters={"parent": ["in", list(boms.values())]}, fields=["parent", "item_code", "qty"]
	)
	per_bom = {}
	for bl in bom_lines:
		per_bom.setdefault(bl.parent, []).append(bl)

	need = {}
	for l in menu_lines:
		bom = boms.get(l["item_code"])
		if not bom:
			continue
		for bl in per_bom.get(bom, []):
			need[bl.item_code] = flt(need.get(bl.item_code)) + flt(bl.qty) * flt(l["qty"])
	if not need:
		return {}

	# Keep only is_stock_item==1 raws (batched); drop + log the rest so one non-stock raw
	# can't abort the Material Issue and lose every valid line (Reviewer #2).
	raw_codes = list(need)
	stock_flags = {
		r.name: cint(r.is_stock_item)
		for r in frappe.get_all(
			"Item", filters={"name": ["in", raw_codes]}, fields=["name", "is_stock_item"]
		)
	}
	dropped = [c for c in raw_codes if not stock_flags.get(c)]
	if dropped:
		frappe.log_error(
			"Skipped non-stock BOM raw material(s) in comp stock reversal: " + ", ".join(dropped),
			"pos_next comp non-stock raw",
		)
	return {c: q for c, q in need.items() if stock_flags.get(c)}


def _comp_reverse_stock(comp_name, pos_profile=None):
	"""Issue ONE Material Issue reversing the comped order's stock (LOCKED Q2 = BOTH):
	is_stock_item lines are issued directly; non-stock menu lines consume their default
	BOM raw materials. Both are aggregated into a single Stock Entry linked back via
	custom_pos_comp_order.

	Idempotent: a re-fire (double click / retry / re-submit) returns None because a
	submitted Stock Entry already carries this comp's link. Returns None when there is
	nothing to reverse (all lines non-stock without a BOM)."""
	if frappe.db.exists("Stock Entry", {"custom_pos_comp_order": comp_name, "docstatus": 1}):
		return None

	co = frappe.get_doc("POS Complimentary Order", comp_name)
	pos_profile = pos_profile or co.pos_profile
	company, warehouse, cost_center = _comp_stock_context(pos_profile)

	lines = [
		{"item_code": r.item_code, "qty": flt(r.qty)}
		for r in co.items
		if r.item_code and flt(r.qty) > 0
	]
	if not lines:
		return None

	codes = list({l["item_code"] for l in lines})
	is_stock = {
		r.name: cint(r.is_stock_item)
		for r in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "is_stock_item"])
	}
	direct = [l for l in lines if is_stock.get(l["item_code"])]
	non_stock = [l for l in lines if not is_stock.get(l["item_code"])]

	need = {}
	for l in direct:
		need[l["item_code"]] = flt(need.get(l["item_code"])) + flt(l["qty"])
	for code, qty in _bom_raw_needs(non_stock).items():
		need[code] = flt(need.get(code)) + flt(qty)
	if not need:
		return None

	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"purpose": "Material Issue",
			"company": company,
			"custom_pos_comp_order": comp_name,
			"remarks": _("Stock reversal for complimentary order {0}").format(comp_name),
			# allow_zero_valuation_rate: a bin may be empty/negative on some sites — issue
			# at zero valuation instead of blocking the reversal (Kaapqah pattern).
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"s_warehouse": warehouse,
					"cost_center": cost_center,
					"allow_zero_valuation_rate": 1,
				}
				for code, qty in need.items()
			],
		}
	)
	se.flags.ignore_permissions = True
	se.insert(ignore_permissions=True)
	se.submit()
	co.db_set("stock_entry", se.name)
	return se.name


def _comp_stock_return(comp_name):
	"""Cancel every submitted Material Issue linked to this comp -> stock back. Idempotent
	via the docstatus=1 filter: a re-reject / already-cancelled comp is a no-op
	(mirror Kaapqah inventory.reverse_free_order_stock)."""
	for name in frappe.get_all(
		"Stock Entry", filters={"custom_pos_comp_order": comp_name, "docstatus": 1}, pluck="name"
	):
		se = frappe.get_doc("Stock Entry", name)
		se.flags.ignore_permissions = True
		se.cancel()


def _comp_line_rate(item_code, provided=None, pos_profile=None):
	"""Free-order line rate is display-only. Resolve the rate server-side first (spec §86),
	fall back to the client-provided rate, then Item.standard_rate, then 0 — never hard-fail
	a comp on a missing price (Kaapqah pattern)."""
	try:
		return flt(_resolve_rate(item_code, pos_profile))
	except Exception:
		pass
	if provided not in (None, ""):
		return flt(provided)
	return flt(frappe.db.get_value("Item", item_code, "standard_rate") or 0)


def _comp_result(comp_name, replayed=False):
	"""Standard endpoint payload for a comp doc — one shape for a fresh submit and for an
	idempotent replay so the client handles both identically."""
	d = (
		frappe.db.get_value(
			"POS Complimentary Order", comp_name, ["status", "stock_entry", "total_value"], as_dict=True
		)
		or {}
	)
	return {
		"comp_order": comp_name,
		"status": d.get("status") or "Pending",
		"stock_entry": d.get("stock_entry"),
		"total_value": flt(d.get("total_value")),
		"replayed": replayed,
	}


@frappe.whitelist()
def submit_complimentary_order(
	items, reason, reason_note=None, customer=None, table_label=None, pos_profile=None, idempotency_key=None
):
	"""Complimentary / void the current dine-in order. Creates NO Sales Invoice
	(nothing reaches ZATCA). Records a POS Complimentary Order (status Pending) and
	issues the stock reversal AT CREATION (LOCKED Q1 — the food/drink is physically
	gone the moment it is comped; approval is an accounting record). A stock hiccup is
	logged AND surfaced to the caller but must never lose the comp record."""
	frappe.has_permission("POS Complimentary Order", "create", throw=True)
	if isinstance(items, str):
		items = json.loads(items)
	items = [it for it in (items or []) if flt(it.get("qty")) > 0]
	if not items:
		frappe.throw(_("No items to record"))
	if not reason:
		frappe.throw(_("A reason is required for a complimentary order"))

	# Endpoint double-submit guard (Reviewer #4): a re-fired submit (double-click / retry /
	# proxy replay) carrying the same client key must NOT create a second comp + a second
	# Material Issue (double stock depletion). idempotency_key is a UNIQUE field on the
	# doctype, so the DB is the hard guard even under truly concurrent inserts; the
	# get_value below is the fast replay path. No key (legacy calls) => guard is inert.
	key = cstr(idempotency_key) or None
	if key:
		existing = frappe.db.get_value("POS Complimentary Order", {"idempotency_key": key}, "name")
		if existing:
			return _comp_result(existing, replayed=True)

	# Normalise table_label to the canonical human label (POS Table.table_name) when the
	# caller passed a POS Table name (Reviewer #6b) — keeps the desk record readable and
	# consistent with the session/KOT table_label.
	if table_label and frappe.db.exists("POS Table", table_label):
		table_label = frappe.db.get_value("POS Table", table_label, "table_name") or table_label

	co = frappe.new_doc("POS Complimentary Order")
	co.pos_profile = pos_profile
	co.table_label = table_label
	co.customer = customer if (customer and customer != "Walk-in Customer") else None
	co.staff = frappe.session.user
	co.ordered_at = now_datetime()
	co.reason = reason
	co.reason_note = reason_note
	co.status = "Pending"
	co.idempotency_key = key
	for it in items:
		code = it["item_code"]
		rate = _comp_line_rate(code, it.get("rate"), pos_profile)
		qty = flt(it["qty"])
		co.append(
			"items",
			{
				"item_code": code,
				"item_name": frappe.db.get_value("Item", code, "item_name") or code,
				"qty": qty,
				"rate": rate,
				"amount": rate * qty,
				"notes": it.get("notes") or "",
			},
		)
	try:
		co.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		# Lost a concurrent race on the idempotency key — return the winning comp.
		frappe.db.rollback()
		winner = frappe.db.get_value("POS Complimentary Order", {"idempotency_key": key}, "name")
		if winner:
			return _comp_result(winner, replayed=True)
		raise

	# Stock out at creation. Guarded — a stock hiccup must not lose the comp record
	# (admin sees an empty stock_entry and can re-issue). _comp_reverse_stock persists
	# the SE onto the comp via db_set, so _comp_result reads it back from the DB below.
	stock_error = False
	try:
		_comp_reverse_stock(co.name, pos_profile)
	except Exception:
		stock_error = True
		frappe.log_error(frappe.get_traceback(), "comp order stock " + cstr(co.name))

	frappe.db.commit()
	_publish(TABLE_EVENT, {"table_label": table_label, "comp_order": co.name, "action": "comp"})
	result = _comp_result(co.name)
	if stock_error:
		# Comp recorded but its expected stock reversal did not complete — surface it
		# (Reviewer #5) instead of returning silent success; admin re-issues from the doc.
		result["stock_warning"] = _(
			"Complimentary order {0} was recorded, but its stock reversal did not complete. "
			"Please review Stock Entries and re-issue if needed."
		).format(co.name)
	return result


@frappe.whitelist()
def approve_complimentary_order(name, decision, approval_note=None):
	"""Approve or reject a Pending comp. Role-guarded (approver roles only). Only
	Pending -> Approved / Rejected is legal (Approved/Rejected are terminal). The
	controller on_update stamps approved_by/approved_on and, on Rejected, returns the
	stock issued at creation."""
	if decision not in ("Approved", "Rejected"):
		frappe.throw(_("Invalid decision {0}").format(decision))
	_guard_comp_approver()
	doc = frappe.get_doc("POS Complimentary Order", name)
	if doc.status != "Pending":
		frappe.throw(
			_("Complimentary order {0} is already {1}").format(name, _(doc.status))
		)
	doc.status = decision
	if approval_note is not None:
		doc.approval_note = approval_note
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_publish(TABLE_EVENT, {"comp_order": name, "action": "comp_decision", "status": decision})
	return {"comp_order": name, "status": decision}
