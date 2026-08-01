# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Branch-safe chart source for the POS management charts.

Frappe's built-in "Group By" charts on a CHILD table cannot be branch-isolated:
a User Permission on Branch restricts the parent Sales Invoice, but the chart
aggregates `Sales Invoice Item` / `Sales Invoice Payment` rows directly and
never joins the parent, so a branch-restricted cashier was reading every
branch's totals. Neither the chart's own `roles` table nor the workspace's
helps — `dashboard_chart.get()` is whitelisted and does not consult
`has_permission`, so the only reliable place to filter is the query itself.

This source joins the parent invoice and applies the caller's User Permissions,
the same rule used by pos_next.api.dashboard.
"""

import frappe
from frappe.utils import getdate, nowdate
from frappe.utils.dashboard import cache_source
from frappe.utils.dateutils import get_from_date_from_timespan

# frappe.desk.doctype.dashboard_chart.get() does `filters.append(...)` on
# filters_json, so it MUST stay a list — the metric cannot ride in there.
# Derive it from the chart instead.
METRIC_BY_CHART = {
	"Top Selling Items": "top_items",
	"Payment Mode Split": "payment_mode",
}

METRICS = {
	"top_items": {
		"table": "`tabSales Invoice Item`",
		"label_field": "item_name",
		"value_field": "amount",
		"limit": 10,
	},
	"payment_mode": {
		"table": "`tabSales Invoice Payment`",
		"label_field": "mode_of_payment",
		"value_field": "amount",
		"limit": 8,
	},
}


def _branch_conditions():
	"""Restrict to the branches / tills the caller is allowed to see."""
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	perms = get_user_permissions() or {}
	cond, values = [], {}
	for doctype, fieldname in (("Branch", "branch"), ("POS Profile", "pos_profile")):
		allowed = [p.get("doc") for p in (perms.get(doctype) or []) if p.get("doc")]
		if not allowed:
			continue
		keys = []
		for i, value in enumerate(allowed):
			key = "up_%s_%d" % (fieldname, i)
			values[key] = value
			keys.append("%%(%s)s" % key)
		cond.append("si.%s IN (%s)" % (fieldname, ", ".join(keys)))
	return cond, values


@frappe.whitelist()
@cache_source
def get(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
):
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(frappe._("Not permitted to view sales data"), frappe.PermissionError)

	# @cache_source re-invokes this with `chart` already hydrated as a Document,
	# so accept a name, a JSON string, a dict or a Document
	if chart_name:
		chart = frappe.get_doc("Dashboard Chart", chart_name)
	elif isinstance(chart, str):
		chart = frappe._dict(frappe.parse_json(chart))
	elif isinstance(chart, dict):
		chart = frappe._dict(chart)

	filters = frappe.parse_json(filters) or frappe.parse_json(chart.filters_json) or []

	metric_key = None
	company = None
	if isinstance(filters, dict):
		metric_key = filters.get("metric")
		company = filters.get("company")
	elif isinstance(filters, list):
		for row in filters:
			if isinstance(row, list) and len(row) >= 4 and row[1] == "company":
				company = row[3]

	metric_key = metric_key or METRIC_BY_CHART.get(chart.get("name") or chart_name)
	metric = METRICS.get(metric_key)
	if not metric:
		return {"labels": [], "datasets": []}

	to_d = getdate(to_date or nowdate())
	from_d = getdate(from_date) if from_date else getdate(
		get_from_date_from_timespan(str(to_d), chart.timespan or "Last Month")
	)

	where = [
		"si.docstatus = 1",
		"si.is_pos = 1",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	values = {"from_date": from_d, "to_date": to_d}

	company = company or frappe.defaults.get_user_default("Company")
	if company:
		where.append("si.company = %(company)s")
		values["company"] = company

	branch_cond, branch_values = _branch_conditions()
	where.extend(branch_cond)
	values.update(branch_values)

	rows = frappe.db.sql(
		"""
		SELECT child.{label} AS k, COALESCE(SUM(child.{value}), 0) AS v
		FROM {table} child
		INNER JOIN `tabSales Invoice` si ON si.name = child.parent
		WHERE {where}
		GROUP BY child.{label}
		ORDER BY v DESC
		LIMIT {limit}
		""".format(
			label=metric["label_field"],
			value=metric["value_field"],
			table=metric["table"],
			where=" AND ".join(where),
			limit=int(metric["limit"]),
		),
		values,
		as_dict=True,
	)

	return {
		"labels": [r.k for r in rows if r.k],
		"datasets": [{"name": chart.get("chart_name") or "Total", "values": [r.v for r in rows if r.k]}],
	}
