# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Day summary for the POS screen — the DCR, scoped to the till the cashier is on.

The DCR itself is a desk Script Report whose roles are Accounts Manager /
Accounts User / Nexus POS Manager / System Manager, so a cashier can never open
it. They still need to know what their own drawer did today, which is what this
endpoint is for: same numbers, same code path, narrowed to the POS Profiles the
caller is actually allowed to see.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from pos_next.pos_next.report.dcr_report.dcr_report import execute as dcr_execute


def _scope_profiles():
	"""POS Profiles this user may see numbers for, narrowest rule first.

	1. User Permissions on POS Profile — the same records that drive branch
	   isolation everywhere else, so there is one rule, not two.
	2. Otherwise the tills they are allowed to operate (Applicable for Users).
	3. Otherwise whatever they can read — managers with no restrictions.
	"""
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	perms = get_user_permissions() or {}
	allowed = [p.get("doc") for p in (perms.get("POS Profile") or []) if p.get("doc")]
	if allowed:
		return sorted(set(allowed))

	mine = frappe.get_all("POS Profile User", filters={"user": frappe.session.user}, pluck="parent")
	mine = [m for m in mine if m]
	if mine:
		return sorted(set(mine))

	return frappe.get_list("POS Profile", pluck="name")


@frappe.whitelist()
def get_day_summary(pos_profile=None, from_date=None, to_date=None):
	"""DCR rows for one till and one date range (defaults to today)."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted to view sales data"), frappe.PermissionError)

	allowed = _scope_profiles()
	if not allowed:
		frappe.throw(_("No POS Profile is available for your user"), frappe.PermissionError)

	if pos_profile:
		# never trust the profile the client asks for
		if pos_profile not in allowed:
			frappe.throw(_("Not permitted to view this POS Profile"), frappe.PermissionError)
	else:
		pos_profile = allowed[0]

	profile = frappe.db.get_value("POS Profile", pos_profile, ["company", "branch"], as_dict=True)
	if not profile:
		frappe.throw(_("POS Profile not found"))

	from_d = getdate(from_date) if from_date else getdate(nowdate())
	to_d = getdate(to_date) if to_date else from_d
	if from_d > to_d:
		from_d, to_d = to_d, from_d

	filters = {
		"company": profile.company,
		"from_date": from_d,
		"to_date": to_d,
		"pos_profile": pos_profile,
		"branch": profile.get("branch"),
	}
	columns, rows = dcr_execute(filters)

	return {
		"pos_profile": pos_profile,
		"branch": profile.get("branch"),
		"company": profile.company,
		"currency": frappe.get_cached_value("Company", profile.company, "default_currency"),
		"from_date": str(from_d),
		"to_date": str(to_d),
		"columns": columns,
		"rows": rows,
		"profiles": allowed,
	}
