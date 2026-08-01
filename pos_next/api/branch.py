# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch resolution and stamping for POS transactions.

`branch` is registered as an Accounting Dimension by Branch Configuration.
Because `AccountsController.get_gl_dict()` reads accounting dimensions from the
document header, setting `doc.branch` once means every GL row of the voucher
(income, tax, receivable, cash, rounding) carries the branch. A cost center
cannot do this: it is an item-row property, so tax and payment rows fall back
to company defaults.

All helpers no-op when the site has no Branch Configuration records, so this is
inert on single-branch installs.
"""

import frappe


def get_branch_config(pos_profile: str | None = None, branch: str | None = None):
	"""Return the Branch Configuration for a POS Profile or Branch (cached)."""
	if not pos_profile and not branch:
		return None
	filters = {"disabled": 0}
	if pos_profile:
		filters["pos_profile"] = pos_profile
	else:
		filters["branch"] = branch
	name = frappe.db.get_value("Branch Configuration", filters, "name")
	if not name:
		return None
	return frappe.get_cached_doc("Branch Configuration", name)


def apply_branch_defaults(doc, method=None):
	"""before_insert: stamp branch, cost center, warehouse and naming series.

	Only fills values the user has not already set, so manual overrides stick.
	"""
	if not _branches_configured():
		return

	config = get_branch_config(pos_profile=doc.get("pos_profile")) or (
		get_branch_config(branch=doc.get("branch")) if doc.get("branch") else None
	)
	if not config:
		return

	if not doc.get("branch") and doc.meta.get_field("branch"):
		doc.branch = config.branch
	if config.cost_center and not doc.get("cost_center"):
		doc.cost_center = config.cost_center
	if config.warehouse and doc.meta.get_field("set_warehouse") and not doc.get("set_warehouse"):
		doc.set_warehouse = config.warehouse
	if config.naming_series_prefix and doc.meta.get_field("naming_series"):
		series = f"{config.naming_series_prefix}-.YYYY.-"
		if doc.naming_series != series:
			doc.naming_series = series


def apply_branch_to_items(doc, method=None):
	"""validate: propagate the header branch/cost center onto item rows.

	Keeps item-level cost centers consistent with the branch so cost-center
	reports agree with branch reports.
	"""
	if not doc.get("branch") and not doc.get("cost_center"):
		return
	for item in doc.get("items") or []:
		if doc.get("branch") and item.meta.get_field("branch") and not item.get("branch"):
			item.branch = doc.branch
		if doc.get("cost_center") and not item.get("cost_center"):
			item.cost_center = doc.cost_center


def _branches_configured() -> bool:
	"""True when this site actually uses branches."""
	return bool(
		frappe.get_all("Branch Configuration", filters={"disabled": 0}, limit=1, ignore_permissions=True)
	)


@frappe.whitelist()
def get_branch_for_pos_profile(pos_profile: str):
	"""Expose the branch mapping to the POS frontend."""
	if not frappe.has_permission("POS Profile", "read", doc=pos_profile):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	config = get_branch_config(pos_profile=pos_profile)
	if not config:
		return {}
	return {
		"branch": config.branch,
		"cost_center": config.cost_center,
		"warehouse": config.warehouse,
		"abbr": config.abbr,
		"crn": config.crn,
		"address": config.address,
	}
