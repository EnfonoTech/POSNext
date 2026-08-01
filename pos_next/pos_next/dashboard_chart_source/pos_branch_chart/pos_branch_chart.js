frappe.provide('frappe.dashboards.chart_sources');

frappe.dashboards.chart_sources['POS Branch Chart'] = {
	method: 'pos_next.pos_next.dashboard_chart_source.pos_branch_chart.pos_branch_chart.get',
	filters: [],
};
