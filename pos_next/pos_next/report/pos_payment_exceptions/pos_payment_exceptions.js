// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.query_reports["POS Payment Exceptions"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "pos_profile",
			label: __("Till"),
			fieldtype: "Link",
			options: "POS Profile",
		},
		{
			fieldname: "only_open",
			label: __("Only Uncorrected"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "issue" && data && data.issue) {
			// Overpaid is the money-at-risk case; short-paid means cash never collected.
			const colour = data.issue === __("Short paid") ? "orange" : "red";
			value = `<span style="color:${colour};font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "difference" && data && data.difference) {
			value = `<span style="color:red">${value}</span>`;
		}
		return value;
	},
};
