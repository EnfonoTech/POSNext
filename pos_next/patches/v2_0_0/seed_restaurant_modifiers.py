"""Seed sample menu-item modifier groups for the Restaurant module.

Idempotent data patch (human gate decision: SEED SAMPLES). Creates two sample
POS Modifier Groups (Size, Extras) with their options if they do not already
exist, and attaches BOTH to the demo item ESPRESSO — but only if that item
exists and the custom field is present. Guarded by existence checks throughout,
so a second migrate (or a site without the demo item) is a clean no-op: no
duplicate groups, options, or item links.
"""

import frappe

DEMO_ITEM = "ESPRESSO"
MODIFIER_FIELD = "custom_modifier_groups"

GROUPS = {
	"Size": {
		"selection_type": "Single",
		"is_required": 1,
		"min_select": 0,
		"max_select": 0,
		"options": [
			{"option_label": "Regular", "price_delta": 0, "is_default": 1},
			{"option_label": "Large", "price_delta": 5.00},
		],
	},
	"Extras": {
		"selection_type": "Multiple",
		"is_required": 0,
		"min_select": 0,
		"max_select": 0,
		"options": [
			{"option_label": "Extra Shot", "price_delta": 3.00},
			{"option_label": "Whipped Cream", "price_delta": 2.00},
			{"option_label": "Oat Milk", "price_delta": 2.50},
		],
	},
}


def execute():
	for group_name, cfg in GROUPS.items():
		_ensure_group(group_name, cfg)
	_attach_to_demo_item()


def _ensure_group(group_name, cfg):
	if frappe.db.exists("POS Modifier Group", group_name):
		return
	doc = frappe.get_doc(
		{
			"doctype": "POS Modifier Group",
			"group_name": group_name,
			"selection_type": cfg["selection_type"],
			"is_required": cfg["is_required"],
			"min_select": cfg["min_select"],
			"max_select": cfg["max_select"],
			"options": cfg["options"],
		}
	)
	doc.insert(ignore_permissions=True)


def _attach_to_demo_item():
	# Production-safe: no demo item -> nothing to attach.
	if not frappe.db.exists("Item", DEMO_ITEM):
		return
	# post_model_sync patches run BEFORE sync_fixtures() on migrate (v15
	# migrate.py: sync_all -> post_model_sync patches -> sync_fixtures), so on the
	# migrate that introduces this version the fixture-shipped Custom Field does not
	# exist yet when this patch runs. Create it in-patch (idempotent) so the attach
	# actually happens; sync_fixtures() later reconciles it to the fixture.
	_ensure_modifier_field()

	item = frappe.get_doc("Item", DEMO_ITEM)
	existing = {row.modifier_group for row in item.get(MODIFIER_FIELD)}
	changed = False
	for group_name in GROUPS:
		if group_name not in existing:
			item.append(MODIFIER_FIELD, {"modifier_group": group_name})
			changed = True
	if changed:
		item.save(ignore_permissions=True)


def _ensure_modifier_field():
	"""Idempotently create the Item custom field this patch attaches to. Mirrors
	the fixture (pos_next/fixtures/custom_field.json); sync_fixtures() reconciles
	it afterwards. No-op if it already exists."""
	if frappe.get_meta("Item").has_field(MODIFIER_FIELD):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": MODIFIER_FIELD,
					"label": "Customization / Modifier Groups",
					"fieldtype": "Table",
					"options": "POS Item Modifier",
					"insert_after": "description",
					"description": "Ordered list of modifier groups offered for this item (e.g. Size, Extras).",
				}
			]
		}
	)
