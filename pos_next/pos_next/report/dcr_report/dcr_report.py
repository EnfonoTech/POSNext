# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""DCR — Daily Cash Report for POS branches.

Answers the question a branch manager asks at close of day: what came in, in
which tender, what went out, and does the drawer agree with the system.

Structure follows the DCR convention used elsewhere in the group (Particulars /
Income / Expense, opening and closing cash bracketing the movement), adapted for
POS: sales are split by mode of payment from the invoice payment rows rather
than by settlement against receivables, and the counted drawer comes from POS
Closing Shift so the variance is visible on the same sheet.

Cash opening/closing are read from the General Ledger cash accounts of the
branch, so a journal entry posted outside the POS still moves the balance.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Please select a Company"))
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("Please select From Date and To Date"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted to view sales data"), frappe.PermissionError)

	data = get_data(filters)
	return get_columns(), data


def get_columns():
	return [
		{"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data", "width": 280},
		{"label": _("Income"), "fieldname": "income", "fieldtype": "Currency", "width": 130},
		{"label": _("Expense"), "fieldname": "expense", "fieldtype": "Currency", "width": 130},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 120},
	]


# ---------------------------------------------------------------- helpers
def _conditions(filters, alias="si"):
	"""Shared WHERE for submitted POS invoices in scope."""
	cond = [
		f"{alias}.docstatus = 1",
		f"{alias}.is_pos = 1",
		f"{alias}.company = %(company)s",
		f"{alias}.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"branch": filters.branch,
		"pos_profile": filters.pos_profile,
	}
	if filters.branch and frappe.get_meta("Sales Invoice").get_field("branch"):
		cond.append(f"{alias}.branch = %(branch)s")
	if filters.pos_profile:
		cond.append(f"{alias}.pos_profile = %(pos_profile)s")
	return " AND ".join(cond), values


def get_branch_cash_accounts(filters):
	"""Cash-type accounts used by this branch's tills.

	Derived from the Modes of Payment on the branch's POS Profile(s): a POS
	profile always names the account its cash drawer posts to, so that account
	is the branch's cash balance by definition.
	"""
	profiles = []
	if filters.pos_profile:
		profiles = [filters.pos_profile]
	elif filters.branch and frappe.db.exists("DocType", "Branch Configuration"):
		profiles = frappe.get_all(
			"Branch Configuration",
			filters={"branch": filters.branch, "disabled": 0},
			pluck="pos_profile",
		)
		profiles = [p for p in profiles if p]
	if not profiles:
		return []

	rows = frappe.get_all(
		"POS Payment Method",
		filters={"parent": ["in", profiles]},
		fields=["mode_of_payment"],
	)
	modes = [r.mode_of_payment for r in rows if r.mode_of_payment]
	if not modes:
		return []

	accounts = frappe.get_all(
		"Mode of Payment Account",
		filters={"parent": ["in", modes], "company": filters.company},
		fields=["default_account", "parent"],
	)
	cash_modes = set(
		frappe.get_all("Mode of Payment", filters={"name": ["in", modes], "type": "Cash"}, pluck="name")
	)
	return sorted({a.default_account for a in accounts if a.default_account and a.parent in cash_modes})


def get_cash_balance(as_of_date, filters):
	"""GL balance of the branch cash accounts as of a date."""
	accounts = get_branch_cash_accounts(filters)
	if not accounts:
		return 0.0
	rows = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0)
		FROM `tabGL Entry` gle
		WHERE gle.is_cancelled = 0
			AND gle.company = %(company)s
			AND gle.posting_date <= %(as_of_date)s
			AND gle.account IN %(accounts)s
		""",
		{"company": filters.company, "as_of_date": as_of_date, "accounts": tuple(accounts)},
	)
	return flt(rows[0][0]) if rows else 0.0


def get_sales_by_mode(filters):
	"""Settled amount per mode of payment, from the invoice payment rows."""
	where, values = _conditions(filters)
	return frappe.db.sql(
		f"""
		SELECT sip.mode_of_payment AS mode,
			COALESCE(SUM(sip.amount), 0) AS amount,
			COUNT(DISTINCT si.name) AS invoices
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE {where} AND si.is_return = 0
		GROUP BY sip.mode_of_payment
		ORDER BY amount DESC
		""",
		values,
		as_dict=True,
	)


def get_totals(filters, is_return=0):
	where, values = _conditions(filters)
	row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(si.grand_total), 0) AS total,
			COALESCE(SUM(si.net_total), 0) AS net,
			COALESCE(SUM(si.total_taxes_and_charges), 0) AS tax,
			COALESCE(SUM(si.discount_amount), 0) AS discount,
			COUNT(si.name) AS cnt
		FROM `tabSales Invoice` si
		WHERE {where} AND si.is_return = %(is_return)s
		""",
		dict(values, is_return=cint(is_return)),
		as_dict=True,
	)
	return row[0] if row else frappe._dict(total=0, net=0, tax=0, discount=0, cnt=0)


def get_shift_counted(filters):
	"""What the cashiers actually counted, per POS Closing Shift in range."""
	cond = ["cs.docstatus = 1", "cs.period_end_date BETWEEN %(from_date)s AND %(to_date)s"]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.pos_profile:
		cond.append("cs.pos_profile = %(pos_profile)s")
		values["pos_profile"] = filters.pos_profile
	elif filters.branch and frappe.db.exists("DocType", "Branch Configuration"):
		profiles = frappe.get_all(
			"Branch Configuration", filters={"branch": filters.branch, "disabled": 0}, pluck="pos_profile"
		)
		profiles = [p for p in profiles if p]
		if profiles:
			cond.append("cs.pos_profile IN %(profiles)s")
			values["profiles"] = tuple(profiles)
	rows = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(d.closing_amount), 0) AS counted,
			COALESCE(SUM(d.expected_amount), 0) AS expected,
			COUNT(DISTINCT cs.name) AS shifts
		FROM `tabPOS Closing Shift Detail` d
		INNER JOIN `tabPOS Closing Shift` cs ON cs.name = d.parent
		WHERE {cond}
		""".format(cond=" AND ".join(cond)),
		values,
		as_dict=True,
	)
	return rows[0] if rows else frappe._dict(counted=0, expected=0, shifts=0)


# ---------------------------------------------------------------- data
def get_data(filters):
	sales = get_totals(filters, is_return=0)
	returns = get_totals(filters, is_return=1)
	modes = get_sales_by_mode(filters)
	counted = get_shift_counted(filters)

	opening = get_cash_balance(add_days(getdate(filters.from_date), -1), filters)
	closing = get_cash_balance(filters.to_date, filters)

	def row(label, indent=0, income=None, expense=None, invoices=None, variance=None):
		return {
			"particulars": label,
			"indent": indent,
			"income": income,
			"expense": expense,
			"invoices": invoices,
			"variance": variance,
		}

	data = [row(_("Opening Cash Balance"), 0, income=opening)]

	data.append(row(_("Sales Collected"), 0, income=flt(sales.total), invoices=cint(sales.cnt)))
	for m in modes:
		data.append(row(m.mode or _("Unspecified"), 1, income=flt(m.amount), invoices=cint(m.invoices)))

	if flt(returns.total):
		data.append(row(_("Sales Returns"), 0, expense=abs(flt(returns.total)), invoices=cint(returns.cnt)))

	data.append(row(_("Net Sales (excl. VAT)"), 0, income=flt(sales.net) + flt(returns.net)))
	data.append(row(_("VAT Collected"), 0, income=flt(sales.tax) + flt(returns.tax)))
	if flt(sales.discount):
		data.append(row(_("Discounts Given"), 0, expense=flt(sales.discount)))

	movement = closing - opening
	data.append(row(_("Net Cash Movement"), 0, income=movement if movement >= 0 else None,
					expense=abs(movement) if movement < 0 else None))
	data.append(row(_("Closing Cash Balance"), 0, income=closing))

	if cint(counted.shifts):
		variance = flt(counted.counted) - flt(counted.expected)
		data.append(row(_("Counted in Drawer ({0} shifts)").format(cint(counted.shifts)), 0,
						income=flt(counted.counted), variance=variance))
		data.append(row(_("System Expected"), 1, income=flt(counted.expected)))

	return data
