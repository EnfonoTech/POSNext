import frappe


def execute():
	"""Remove the BrainWise Branding DocType and its data.

	The branding/tamper-protection subsystem was removed from the app;
	sites upgrading in place would otherwise keep an orphaned DocType
	whose controller module no longer exists.
	"""
	frappe.delete_doc("DocType", "BrainWise Branding", force=True, ignore_missing=True)
