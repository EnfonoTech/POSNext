"""
Role permissions for the two POS roles, granted the way Frappe's own Role Permission Manager does it.

Why this is code and not a Custom DocPerm fixture
-------------------------------------------------
Frappe treats Custom DocPerm as all-or-nothing per DocType: as soon as ONE Custom DocPerm row exists for a
DocType, the standard DocPerm rows of that DocType are ignored (frappe.permissions.get_valid_perms). That is why
frappe.permissions.add_permission() first copies every standard row into Custom DocPerm (setup_custom_perms).

The old fixture inserted one bare row per DocType, so on every site that installed pos_next the standard roles
(Accounts User, Accounts Manager, Sales User, Stock User, ...) lost their rights on Journal Entry, Sales Invoice,
Payment Entry, Item, Account, Customer, Warehouse and the rest of GRANTS. Journal Entry was left with a single
read-only row, so the desk form was read-only for everybody, Administrator included.

ensure_role_permissions() (after_install + after_migrate):
  1. puts back the standard rows of a DocType whose Custom DocPerm rows are ONLY our POS roles (the fixture's
     damage). A DocType a site has customised on purpose (any other role has a Custom DocPerm row) is left as is.
  2. copies the standard rows first when the DocType has no Custom DocPerm yet (same as add_permission).
  3. adds or raises the POS role's row to the flags below. Flags are only switched on, never off, so a right a site
     manager gave on top is kept.
Idempotent: a second run changes nothing.
"""

import frappe

POS_ROLES = ("POSNext Cashier", "Nexus POS Manager")

PERM_FLAGS = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"print",
	"email",
	"share",
)

# (DocType, role) -> flags switched on at permlevel 0: exactly the rights the old fixture granted.
GRANTS = {
	("Account", "POSNext Cashier"): ("select", "read", "export"),
	("Bin", "POSNext Cashier"): ("select", "read", "report"),
	("Customer", "POSNext Cashier"): ("select", "read", "write", "create", "report", "export", "print"),
	("Item", "POSNext Cashier"): ("select", "read", "report"),
	# POS Expense Report; the list is limited to POS expenses by
	# pos_next.api.expenses.get_journal_entry_permission_query_conditions.
	("Journal Entry", "Nexus POS Manager"): ("select", "read", "report", "export", "print"),
	("POS Closing Entry", "POSNext Cashier"): ("read", "write", "create", "submit", "cancel", "amend", "report", "export", "print"),
	("POS Opening Entry", "POSNext Cashier"): ("read", "write", "create", "amend", "export"),
	("POS Profile", "POSNext Cashier"): ("read", "export"),
	("Payment Entry", "POSNext Cashier"): ("read", "write", "create", "submit", "export"),
	("Promotional Scheme", "POSNext Cashier"): ("read", "export"),
	("Sales Invoice", "POSNext Cashier"): ("read", "write", "create", "submit", "cancel", "amend", "report", "export", "print"),
	("Serial and Batch Bundle", "POSNext Cashier"): ("read", "write", "create", "delete", "submit", "cancel", "export"),
	("Territory", "POSNext Cashier"): ("read", "export"),
	("Warehouse", "POSNext Cashier"): ("select", "read", "report"),
}


def ensure_role_permissions(quiet=False):
	"""Grant GRANTS without hiding the standard roles' rights. Returns {"restored": [...], "granted": [...]}."""
	_ensure_roles()
	restored, granted = [], []
	for doctype in sorted({dt for dt, _role in GRANTS}):
		if not frappe.db.exists("DocType", doctype):
			continue
		if _restore_standard_rows(doctype):
			restored.append(doctype)
		for (dt, role), flags in GRANTS.items():
			if dt == doctype and _grant(doctype, role, flags):
				granted.append(f"{doctype}: {role}")
	if restored or granted:
		frappe.clear_cache()
	if not quiet and (restored or granted):
		print(f"POSNext permissions: standard rows restored on {restored or 'none'}; grants set {granted or 'none'}")
	return {"restored": restored, "granted": granted}


def _ensure_roles():
	"""install_app runs after_install BEFORE sync_fixtures, so on a fresh install the roles from role.json do not
	exist yet. Create them with the fixture's settings; the fixture sync that follows finds them in place."""
	for role in POS_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def _custom_rows(doctype):
	return frappe.get_all(
		"Custom DocPerm", filters={"parent": doctype}, fields=["name", "role", "permlevel", "if_owner"]
	)


def _restore_standard_rows(doctype):
	"""Copy the DocType's standard DocPerm rows into Custom DocPerm when the only custom rows are POS roles.

	True when rows were copied. No custom rows at all also copies (exactly what setup_custom_perms does before
	a grant), so the POS row never becomes the DocType's only rule.
	"""
	custom = _custom_rows(doctype)
	if any(r.role not in POS_ROLES for r in custom):
		return False  # the site has its own Custom DocPerm on this DocType: respect it
	have = {(r.role, r.permlevel, r.if_owner) for r in custom}
	copied = False
	for d in frappe.get_all("DocPerm", filters={"parent": doctype}, fields="*"):
		if (d.role, d.permlevel, d.if_owner) in have:
			continue
		row = frappe.new_doc("Custom DocPerm")
		row.update(d)
		row.name = None
		row.insert(ignore_permissions=True)
		copied = True
	return copied


def _grant(doctype, role, flags):
	"""Make sure the role's permlevel-0 row has every flag in `flags` switched on. True when something changed."""
	name = frappe.db.get_value(
		"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}, "name"
	)
	if not name:
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": 0,
				**{f: 1 for f in flags},
			}
		).insert(ignore_permissions=True)
		return True
	current = frappe.db.get_value("Custom DocPerm", name, list(flags), as_dict=True)
	missing = {f: 1 for f in flags if not current.get(f)}
	if missing:
		frappe.db.set_value("Custom DocPerm", name, missing)
		return True
	return False
