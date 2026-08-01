// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.query_reports["DCR Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "pos_profile",
			label: __("POS Profile"),
			fieldtype: "Link",
			options: "POS Profile",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.indent === 0) {
			value = `<b>${value}</b>`;
		}
		if (column.fieldname === "variance" && data && flt(data.variance) !== 0) {
			const colour = flt(data.variance) < 0 ? "red" : "green";
			value = `<span style="color:var(--text-${colour},${colour})">${value}</span>`;
		}
		return value;
	},
};
