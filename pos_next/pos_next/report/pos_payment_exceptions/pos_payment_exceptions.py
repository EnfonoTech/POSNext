# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS Payment Exceptions — bills where the money does not reconcile.

The invoice itself is usually right: correct items, correct VAT, correct total,
already cleared with the tax authority. What is wrong is the *tender* — most
often a card tender keyed larger than the bill.

ERPNext only computes change when a payment row is of type Cash
(`calculate_change_amount`). A card-only tender greater than the bill therefore
produces no change and a NEGATIVE outstanding amount: the customer appears to
hold credit, and the card clearing account is overstated against the acquirer.
Nothing surfaces this — the invoice still reads "Paid".

This report finds those bills and hands the accountant the correcting journal
entry lines, so the fix needs no developer and no change to the invoice.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

# An invoice reconciles when: tendered - change = billed.
TOLERANCE = 0.005


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)
	data = get_data(filters)
	return get_columns(), data


def _validate(filters):
	if not filters.company:
		frappe.throw(_("Please select a Company"))
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("Please select From Date and To Date"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted to view sales data"), frappe.PermissionError)


def get_columns():
	return [
		{
			"label": _("Invoice"),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Data", "width": 110},
		{
			"label": _("Till"),
			"fieldname": "pos_profile",
			"fieldtype": "Link",
			"options": "POS Profile",
			"width": 130,
		},
		{"label": _("Cashier"), "fieldname": "cashier", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": _("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 130},
		{"label": _("Billed"), "fieldname": "billed", "fieldtype": "Currency", "width": 100},
		{"label": _("Tendered"), "fieldname": "tendered", "fieldtype": "Currency", "width": 100},
		{"label": _("Change"), "fieldname": "change_amount", "fieldtype": "Currency", "width": 95},
		{"label": _("Kept"), "fieldname": "kept", "fieldtype": "Currency", "width": 100},
		{"label": _("Difference"), "fieldname": "difference", "fieldtype": "Currency", "width": 105},
		{"label": _("Paid Via"), "fieldname": "paid_via", "fieldtype": "Data", "width": 140},
		{
			"label": _("Debit Account"),
			"fieldname": "debit_account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 170,
		},
		{
			"label": _("Credit Account"),
			"fieldname": "credit_account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 190,
		},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
	]


def _conditions(filters):
	"""Shared WHERE for submitted, non-return POS invoices in scope."""
	cond = [
		"si.docstatus = 1",
		"si.is_pos = 1",
		"si.is_return = 0",
		"si.company = %(company)s",
		"si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"branch": filters.branch,
		"pos_profile": filters.pos_profile,
	}
	if filters.branch and frappe.get_meta("Sales Invoice").get_field("branch"):
		cond.append("si.branch = %(branch)s")
	if filters.pos_profile:
		cond.append("si.pos_profile = %(pos_profile)s")
	return " AND ".join(cond), values


def get_data(filters):
	where, values = _conditions(filters)

	rows = frappe.db.sql(
		f"""
		SELECT si.name AS invoice, si.posting_date, si.branch, si.pos_profile,
			si.owner AS cashier, si.customer, si.debit_to,
			si.grand_total AS billed,
			COALESCE(si.change_amount, 0) AS change_amount,
			si.outstanding_amount,
			COALESCE((
				SELECT SUM(p.amount) FROM `tabSales Invoice Payment` p WHERE p.parent = si.name
			), 0) AS tendered,
			(
				SELECT GROUP_CONCAT(DISTINCT p.mode_of_payment ORDER BY p.idx SEPARATOR ', ')
				FROM `tabSales Invoice Payment` p WHERE p.parent = si.name
			) AS paid_via,
			(
				SELECT p.account FROM `tabSales Invoice Payment` p
				WHERE p.parent = si.name AND p.amount = (
					SELECT MAX(p2.amount) FROM `tabSales Invoice Payment` p2 WHERE p2.parent = si.name
				)
				ORDER BY p.idx LIMIT 1
			) AS credit_account
		FROM `tabSales Invoice` si
		WHERE {where}
		ORDER BY si.posting_date, si.name
		""",
		values,
		as_dict=True,
	)

	only_open = cint(filters.get("only_open", 1))
	data = []
	for r in rows:
		kept = flt(r.tendered) - flt(r.change_amount)
		difference = flt(kept - flt(r.billed), 2)
		outstanding = flt(r.outstanding_amount)

		issue = _classify(outstanding, difference)
		if not issue:
			continue
		if only_open and abs(outstanding) <= TOLERANCE:
			# Already corrected — the ledger reconciles even though the tender
			# line still reads what the cashier keyed.
			continue

		data.append(
			{
				"invoice": r.invoice,
				"posting_date": r.posting_date,
				"branch": r.branch,
				"pos_profile": r.pos_profile,
				"cashier": r.cashier,
				"customer": r.customer,
				"issue": issue,
				"billed": flt(r.billed),
				"tendered": flt(r.tendered),
				"change_amount": flt(r.change_amount),
				"kept": kept,
				"difference": difference,
				"paid_via": r.paid_via,
				"debit_account": r.debit_to,
				"credit_account": r.credit_account,
			}
		)
	return data


def _classify(outstanding, difference):
	"""Name the exception, or None when the bill reconciles.

	`outstanding` is authoritative for the ledger; `difference` catches a tender
	that disagrees with the bill even where the outstanding happens to net out.
	"""
	if outstanding < -TOLERANCE:
		return _("Overpaid")
	if outstanding > TOLERANCE:
		return _("Short paid")
	if abs(difference) > TOLERANCE:
		return _("Tender mismatch")
	return None
