// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Profile", {
	setup(frm) {
		// Enfono: on a site where the app's custom fields are not synced yet (install-app
		// without migrate) the table is missing and set_query throws, which stops the whole
		// form from rendering. Skip instead.
		if (!frm.fields_dict.posa_allowed_expense_accounts) return;
		frm.set_query("account", "posa_allowed_expense_accounts", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
				root_type: "Expense",
			},
		}));
	},
});
