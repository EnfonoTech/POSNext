# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch Configuration — one master per branch.

Binds a Branch to its cost center, warehouse, POS Profile, invoice series and
staff, and makes `Branch` a registered Accounting Dimension so that EVERY GL
row of a transaction (income, tax, receivable, cash, rounding) carries the
branch — which a cost center alone cannot do, because cost center is an
item-row property while an accounting dimension is read from the document
header in `AccountsController.get_gl_dict()`.

Registration is deliberately lazy: the dimension is only created the first
time a Branch Configuration is saved, so installs that never use branches are
left untouched.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document

BRANCH_DIMENSION_DOCTYPE = "Branch"
PREFIX_PATTERN = re.compile(r"^[A-Z0-9]{2,6}$")
# a full series the user typed themselves, e.g. TCS-SI-.YYYY.-
SERIES_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-/.]{0,28}$")
DATE_PLACEHOLDER = re.compile(r"\.(YYYY|YY|MM|DD)\.")


def series_from_prefix(value):
	"""Series for a Branch Configuration prefix.

	A bare prefix (COL) becomes COL-.YYYY.-. A value that already contains a
	date placeholder (TCS-SI-.YYYY.-) is a complete series and is used verbatim,
	so a branch can keep a house series that does not fit PREFIX-.YYYY.-.
	"""
	if not value:
		return None
	value = value.strip().upper()
	return value if DATE_PLACEHOLDER.search(value) else value + "-.YYYY.-"


class BranchConfiguration(Document):
	def validate(self):
		self.normalise()
		self.validate_company_links()
		self.validate_exclusive_mappings()
		self.validate_prefix()
		self.validate_pos_profile_users()

	def on_update(self):
		ensure_branch_dimension()
		self.ensure_naming_series_option()
		self.sync_user_permissions()

	# ------------------------------------------------------------------ validate
	def normalise(self):
		if self.abbr:
			self.abbr = self.abbr.strip().upper()
		if self.naming_series_prefix:
			self.naming_series_prefix = self.naming_series_prefix.strip().upper()

	def validate_company_links(self):
		"""Cost center / warehouse must belong to this company and be leaf nodes."""
		for fieldname, doctype in (("cost_center", "Cost Center"), ("warehouse", "Warehouse")):
			value = self.get(fieldname)
			if not value:
				continue
			row = frappe.db.get_value(doctype, value, ["company", "is_group"], as_dict=True)
			if not row:
				continue
			if row.company != self.company:
				frappe.throw(
					_("{0} {1} belongs to company {2}, not {3}").format(
						_(doctype), frappe.bold(value), frappe.bold(row.company), frappe.bold(self.company)
					)
				)
			if row.is_group:
				frappe.throw(
					_("{0} {1} is a group. Select a leaf {0}.").format(_(doctype), frappe.bold(value))
				)

	def validate_exclusive_mappings(self):
		"""A cost center / warehouse / POS Profile may map to only one branch."""
		for fieldname, label in (
			("cost_center", _("Cost Center")),
			("warehouse", _("Warehouse")),
			("pos_profile", _("POS Profile")),
		):
			value = self.get(fieldname)
			if not value:
				continue
			clash = frappe.db.get_value(
				"Branch Configuration",
				{fieldname: value, "name": ["!=", self.name or ""]},
				"name",
			)
			if clash:
				frappe.throw(
					_("{0} {1} is already mapped to branch {2}.").format(
						label, frappe.bold(value), frappe.bold(clash)
					)
				)

	def validate_prefix(self):
		value = self.naming_series_prefix
		if not value:
			return

		if DATE_PLACEHOLDER.search(value):
			# treated as a complete series
			if not SERIES_PATTERN.match(value):
				frappe.throw(
					_("Naming Series {0} is not valid. Use uppercase letters, digits, - / and . only.").format(
						frappe.bold(value)
					)
				)
			return

		if not PREFIX_PATTERN.match(value):
			frappe.throw(
				_(
					"Naming Series Prefix must be 2-6 uppercase letters or digits (e.g. {0}), "
					"or a complete series containing a date placeholder (e.g. {1})."
				).format(frappe.bold("COL"), frappe.bold("TCS-SI-.YYYY.-"))
			)

	def validate_pos_profile_users(self):
		"""Guard the POS Profile <-> branch users overlap.

		A cashier listed here but allowed on a POS Profile belonging to a
		DIFFERENT branch would produce sales attributed to a branch they are not
		assigned to. Surface it instead of letting it happen silently.
		"""
		if not self.users:
			return
		branch_users = {row.user for row in self.users if row.user}
		if not branch_users:
			return

		other_profiles = frappe.get_all(
			"Branch Configuration",
			filters={"name": ["!=", self.name or ""], "pos_profile": ["is", "set"]},
			fields=["name", "pos_profile"],
		)
		for other in other_profiles:
			allowed = {
				row.user
				for row in frappe.get_all(
					"POS Profile User",
					filters={"parent": other.pos_profile},
					fields=["user"],
				)
			}
			overlap = branch_users & allowed
			if overlap:
				frappe.msgprint(
					_("User(s) {0} are listed under branch {1} but are also allowed on POS Profile {2} (branch {3}). Sales they make on that till will be attributed to {3}.").format(
						frappe.bold(", ".join(sorted(overlap))),
						frappe.bold(self.branch),
						frappe.bold(other.pos_profile),
						frappe.bold(other.name),
					),
					title=_("Branch / POS Profile overlap"),
					indicator="orange",
				)

	# ------------------------------------------------------------------ on_update
	def ensure_naming_series_option(self):
		"""Keep the Sales Invoice naming_series options in sync with the master."""
		if not self.naming_series_prefix:
			return
		series = series_from_prefix(self.naming_series_prefix)
		if not series:
			return
		meta = frappe.get_meta("Sales Invoice")
		field = meta.get_field("naming_series")
		if not field:
			return
		options = [opt for opt in (field.options or "").split("\n") if opt]
		if series in options:
			return
		options.append(series)

		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(
			"Sales Invoice",
			"naming_series",
			"options",
			"\n".join(options),
			"Text",
			for_doctype=False,
			validate_fields_for_doctype=False,
		)

	def sync_user_permissions(self):
		"""Create/remove User Permissions on Branch for the listed users."""
		if not self.branch:
			return
		desired = (
			{row.user for row in self.users if row.user} if self.apply_user_permissions else set()
		)
		existing = {
			row.name: row.user
			for row in frappe.get_all(
				"User Permission",
				filters={"allow": BRANCH_DIMENSION_DOCTYPE, "for_value": self.branch},
				fields=["name", "user"],
			)
		}
		for name, user in existing.items():
			if user not in desired:
				frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)

		for user in desired - set(existing.values()):
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": user,
					"allow": BRANCH_DIMENSION_DOCTYPE,
					"for_value": self.branch,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)


def ensure_branch_dimension():
	"""Register `Branch` as an Accounting Dimension (idempotent, lazy).

	Adds the `branch` field to transaction doctypes and GL Entry, and makes a
	Branch filter appear in the standard financial reports.
	"""
	if frappe.db.exists("Accounting Dimension", BRANCH_DIMENSION_DOCTYPE):
		return
	try:
		doc = frappe.get_doc(
			{"doctype": "Accounting Dimension", "document_type": BRANCH_DIMENSION_DOCTYPE}
		)
		doc.insert(ignore_permissions=True)
		frappe.msgprint(
			_("Branch registered as an Accounting Dimension. Branch now appears as a filter in the financial reports."),
			indicator="green",
			alert=True,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Branch Accounting Dimension registration failed")
