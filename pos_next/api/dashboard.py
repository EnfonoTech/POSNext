# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Management dashboard aggregates for FatehPOS."""

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, nowdate, add_days


def _guard():
	"""Only users who may read Sales Invoice can see revenue aggregates."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted to view sales data"), frappe.PermissionError)


def _range(from_date, to_date):
	to_d = getdate(to_date) if to_date else getdate(nowdate())
	from_d = getdate(from_date) if from_date else to_d
	if from_d > to_d:
		from_d, to_d = to_d, from_d
	return from_d, to_d


def _user_permission_conditions():
	"""Restrict aggregates to what the caller's User Permissions allow.

	Every query here is raw SQL, which bypasses the permission layer completely,
	so a branch-restricted cashier would otherwise read every branch's revenue
	straight off /api/method/. Mirror the User Permission records rather than
	inventing a second, divergent rule. A user with no User Permission for a
	link doctype is unrestricted on it, which is how Frappe itself behaves.
	"""
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	perms = get_user_permissions() or {}
	cond, values = [], {}
	for doctype, fieldname in (
		("Branch", "branch"),
		("POS Profile", "pos_profile"),
		("Cost Center", "cost_center"),
		("Company", "company"),
	):
		allowed = [p.get("doc") for p in (perms.get(doctype) or []) if p.get("doc")]
		if not allowed:
			continue
		keys = []
		for i, value in enumerate(allowed):
			key = f"up_{fieldname}_{i}"
			values[key] = value
			keys.append(f"%({key})s")
		cond.append(f"si.{fieldname} IN ({', '.join(keys)})")
	return cond, values


def _conditions(from_d, to_d, company, cost_center):
	cond = ["si.docstatus = 1", "si.is_pos = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]
	values = {"from_date": from_d, "to_date": to_d}
	if company:
		cond.append("si.company = %(company)s")
		values["company"] = company
	if cost_center:
		cond.append("si.cost_center = %(cost_center)s")
		values["cost_center"] = cost_center

	up_cond, up_values = _user_permission_conditions()
	cond.extend(up_cond)
	values.update(up_values)
	return " AND ".join(cond), values


@frappe.whitelist()
def get_dashboard_data(from_date=None, to_date=None, company=None, cost_center=None):
	"""Return KPI totals plus chart series for the management dashboard."""
	_guard()
	from_d, to_d = _range(from_date, to_date)
	where, values = _conditions(from_d, to_d, company, cost_center)

	totals = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(si.grand_total), 0) AS sales,
			COALESCE(SUM(si.net_total), 0) AS net,
			COALESCE(SUM(si.total_taxes_and_charges), 0) AS vat,
			COUNT(si.name) AS invoices,
			COALESCE(AVG(si.grand_total), 0) AS avg_ticket,
			COALESCE(SUM(si.total_qty), 0) AS qty
		FROM `tabSales Invoice` si
		WHERE {where}
		""",
		values,
		as_dict=True,
	)[0]

	# previous period of equal length, for trend arrows
	span = (to_d - from_d).days + 1
	prev_where, prev_values = _conditions(add_days(from_d, -span), add_days(to_d, -span), company, cost_center)
	prev = frappe.db.sql(
		f"SELECT COALESCE(SUM(si.grand_total),0) AS sales, COUNT(si.name) AS invoices "
		f"FROM `tabSales Invoice` si WHERE {prev_where}",
		prev_values,
		as_dict=True,
	)[0]

	trend = frappe.db.sql(
		f"""
		SELECT si.posting_date AS d, COALESCE(SUM(si.grand_total), 0) AS v
		FROM `tabSales Invoice` si WHERE {where}
		GROUP BY si.posting_date ORDER BY si.posting_date
		""",
		values,
		as_dict=True,
	)

	branches = frappe.db.sql(
		f"""
		SELECT COALESCE(si.cost_center, 'Unassigned') AS k, COALESCE(SUM(si.grand_total), 0) AS v
		FROM `tabSales Invoice` si WHERE {where}
		GROUP BY si.cost_center ORDER BY v DESC
		""",
		values,
		as_dict=True,
	)

	payments = frappe.db.sql(
		f"""
		SELECT sip.mode_of_payment AS k, COALESCE(SUM(sip.amount), 0) AS v
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE {where}
		GROUP BY sip.mode_of_payment ORDER BY v DESC
		""",
		values,
		as_dict=True,
	)

	items = frappe.db.sql(
		f"""
		SELECT sii.item_name AS k, COALESCE(SUM(sii.amount), 0) AS v,
			COALESCE(SUM(sii.qty), 0) AS qty
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {where}
		GROUP BY sii.item_name ORDER BY v DESC LIMIT 10
		""",
		values,
		as_dict=True,
	)

	hourly = frappe.db.sql(
		f"""
		SELECT HOUR(si.posting_time) AS k, COALESCE(SUM(si.grand_total), 0) AS v
		FROM `tabSales Invoice` si WHERE {where}
		GROUP BY HOUR(si.posting_time) ORDER BY k
		""",
		values,
		as_dict=True,
	)

	cashiers = frappe.db.sql(
		f"""
		SELECT si.owner AS k, COALESCE(SUM(si.grand_total), 0) AS v, COUNT(si.name) AS c
		FROM `tabSales Invoice` si WHERE {where}
		GROUP BY si.owner ORDER BY v DESC LIMIT 8
		""",
		values,
		as_dict=True,
	)

	def pct(now, before):
		now, before = flt(now), flt(before)
		if not before:
			return None
		return flt((now - before) / before * 100.0, 1)

	return {
		"from_date": str(from_d),
		"to_date": str(to_d),
		"currency": frappe.get_cached_value("Company", company, "default_currency")
		if company
		else frappe.defaults.get_global_default("currency"),
		"kpi": {
			"sales": flt(totals.sales, 2),
			"net": flt(totals.net, 2),
			"vat": flt(totals.vat, 2),
			"invoices": cint(totals.invoices),
			"avg_ticket": flt(totals.avg_ticket, 2),
			"qty": flt(totals.qty, 1),
			"sales_change": pct(totals.sales, prev.sales),
			"invoices_change": pct(totals.invoices, prev.invoices),
		},
		"trend": [{"label": str(r.d), "value": flt(r.v, 2)} for r in trend],
		"branches": [{"label": r.k, "value": flt(r.v, 2)} for r in branches],
		"payments": [{"label": r.k, "value": flt(r.v, 2)} for r in payments],
		"items": [{"label": r.k, "value": flt(r.v, 2), "qty": flt(r.qty, 1)} for r in items],
		"hourly": [{"label": f"{cint(r.k):02d}:00", "value": flt(r.v, 2)} for r in hourly],
		"cashiers": [
			{"label": r.k, "value": flt(r.v, 2), "invoices": cint(r.c)} for r in cashiers
		],
		"prev": {"sales": flt(prev.sales, 2), "invoices": cint(prev.invoices)},
	}


@frappe.whitelist()
def get_filter_options():
	"""Companies and cost centers the user can filter by."""
	_guard()
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	perms = get_user_permissions() or {}
	cc_filters = {"is_group": 0}

	# a user pinned to one or more POS Profiles may only filter by those
	# profiles' cost centers — otherwise the dropdown leaks the branch list
	allowed_profiles = [p.get("doc") for p in (perms.get("POS Profile") or []) if p.get("doc")]
	if allowed_profiles:
		cost_centers = frappe.get_all(
			"POS Profile", filters={"name": ["in", allowed_profiles]}, pluck="cost_center"
		)
		cc_filters["name"] = ["in", [c for c in cost_centers if c] or [""]]

	return {
		# get_list, not get_all: it applies User Permissions
		"companies": frappe.get_list("Company", pluck="name"),
		"cost_centers": frappe.get_list(
			"Cost Center", filters=cc_filters, fields=["name", "company"]
		),
		"default_company": frappe.defaults.get_global_default("company"),
	}
