frappe.pages["fatehpos-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("FatehPOS Dashboard"),
		single_column: true,
	});
	new FatehPOSDashboard(page);
};

class FatehPOSDashboard {
	constructor(page) {
		this.page = page;
		this.charts = {};
		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		const today = frappe.datetime.get_today();
		this.from_date = this.page.add_field({
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(today, -29),
			change: () => this.refresh(),
		});
		this.to_date = this.page.add_field({
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: today,
			change: () => this.refresh(),
		});
		this.company = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			change: () => this.refresh(),
		});
		this.cost_center = this.page.add_field({
			fieldname: "cost_center",
			label: __("Branch (Cost Center)"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({ filters: { is_group: 0 } }),
			change: () => this.refresh(),
		});
		this.from_date.set_input(frappe.datetime.add_days(today, -29));
		this.to_date.set_input(today);

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_menu_item(__("Today"), () => this.quick_range(0));
		this.page.add_menu_item(__("Last 7 Days"), () => this.quick_range(6));
		this.page.add_menu_item(__("Last 30 Days"), () => this.quick_range(29));
	}

	quick_range(days_back) {
		const today = frappe.datetime.get_today();
		this.from_date.set_input(frappe.datetime.add_days(today, -days_back));
		this.to_date.set_input(today);
		this.refresh();
	}

	make_layout() {
		this.page.main.html(`
			<div class="fp-dash">
				<div class="fp-kpis row"></div>
				<div class="row">
					<div class="col-md-8"><div class="fp-card"><div class="fp-card-title">${__("Sales Trend")}</div><div class="fp-chart" id="fp-trend"></div></div></div>
					<div class="col-md-4"><div class="fp-card"><div class="fp-card-title">${__("Payment Mix")}</div><div class="fp-chart" id="fp-pay"></div></div></div>
				</div>
				<div class="row">
					<div class="col-md-6"><div class="fp-card"><div class="fp-card-title">${__("Sales by Branch")}</div><div class="fp-chart" id="fp-branch"></div></div></div>
					<div class="col-md-6"><div class="fp-card"><div class="fp-card-title">${__("Sales by Hour")}</div><div class="fp-chart" id="fp-hour"></div></div></div>
				</div>
				<div class="row">
					<div class="col-md-12"><div class="fp-card"><div class="fp-card-title">${__("Top 10 Items")}</div><div class="fp-top-items"></div></div></div>
				</div>
			</div>
			<style>
				.fp-dash { padding-bottom: 30px; }
				.fp-card { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e5e7eb);
					border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
				.fp-card-title { font-weight: 600; font-size: 13px; color: var(--text-muted, #6b7280);
					text-transform: uppercase; letter-spacing: .4px; margin-bottom: 6px; }
				.fp-kpi { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e5e7eb);
					border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
				.fp-kpi-label { font-size: 12px; color: var(--text-muted, #6b7280); text-transform: uppercase; letter-spacing: .4px; }
				.fp-kpi-value { font-size: 24px; font-weight: 700; margin-top: 4px; }
				.fp-kpi-delta { font-size: 12px; margin-top: 2px; }
				.fp-up { color: #16a34a; } .fp-down { color: #dc2626; } .fp-flat { color: var(--text-muted, #6b7280); }
				.fp-top-items table { width: 100%; font-size: 13px; }
				.fp-top-items td, .fp-top-items th { padding: 6px 4px; border-bottom: 1px solid var(--border-color, #eee); }
				.fp-top-items th { color: var(--text-muted, #6b7280); font-weight: 600; text-align: left; }
				.fp-num { text-align: right; font-variant-numeric: tabular-nums; }
			</style>
		`);
	}

	get_filters() {
		return {
			from_date: this.from_date.get_value(),
			to_date: this.to_date.get_value(),
			company: this.company.get_value(),
			cost_center: this.cost_center.get_value(),
		};
	}

	refresh() {
		frappe.call({
			method: "pos_next.api.dashboard.get_dashboard_data",
			args: this.get_filters(),
			freeze: false,
			callback: (r) => {
				if (!r.message) return;
				this.data = r.message;
				this.render_kpis();
				this.render_charts();
				this.render_items();
			},
		});
	}

	fmt(v) {
		return format_currency(v, this.data.currency);
	}

	render_kpis() {
		const k = this.data.kpi;
		const delta = (val) => {
			if (val === null || val === undefined) return `<div class="fp-kpi-delta fp-flat">—</div>`;
			const cls = val > 0 ? "fp-up" : val < 0 ? "fp-down" : "fp-flat";
			const arrow = val > 0 ? "↑" : val < 0 ? "↓" : "→";
			return `<div class="fp-kpi-delta ${cls}">${arrow} ${Math.abs(val)}% ${__("vs prev period")}</div>`;
		};
		const tile = (label, value, d) => `
			<div class="col-sm-6 col-md-3">
				<div class="fp-kpi">
					<div class="fp-kpi-label">${label}</div>
					<div class="fp-kpi-value">${value}</div>
					${d || ""}
				</div>
			</div>`;
		this.page.main.find(".fp-kpis").html([
			tile(__("Total Sales"), this.fmt(k.sales), delta(k.sales_change)),
			tile(__("Invoices"), k.invoices, delta(k.invoices_change)),
			tile(__("Avg Ticket"), this.fmt(k.avg_ticket)),
			tile(__("VAT Collected"), this.fmt(k.vat)),
		].join(""));
	}

	draw(id, type, labels, values, colors, extra) {
		const el = this.page.main.find(id)[0];
		if (!el) return;
		el.innerHTML = "";
		if (!labels.length) {
			el.innerHTML = `<div class="text-muted" style="padding:28px 0;text-align:center;">${__("No data for this period")}</div>`;
			return;
		}
		this.charts[id] = new frappe.Chart(el, Object.assign({
			data: { labels: labels, datasets: [{ name: __("Sales"), values: values }] },
			type: type,
			height: 240,
			colors: colors,
			axisOptions: { xIsSeries: type === "line" },
			tooltipOptions: { formatTooltipY: (d) => this.fmt(d) },
		}, extra || {}));
	}

	render_charts() {
		const d = this.data;
		this.draw("#fp-trend", "line", d.trend.map((x) => x.label), d.trend.map((x) => x.value), ["#22c55e"], {
			lineOptions: { hideDots: d.trend.length > 40 ? 1 : 0, regionFill: 1 },
		});
		this.draw("#fp-pay", "donut", d.payments.map((x) => x.label), d.payments.map((x) => x.value),
			["#2490EF", "#f59e0b", "#8b5cf6", "#22c55e", "#ef4444"], { height: 240 });
		this.draw("#fp-branch", "bar", d.branches.map((x) => x.label), d.branches.map((x) => x.value), ["#2490EF"]);
		this.draw("#fp-hour", "bar", d.hourly.map((x) => x.label), d.hourly.map((x) => x.value), ["#8b5cf6"]);
	}

	render_items() {
		const rows = this.data.items;
		if (!rows.length) {
			this.page.main.find(".fp-top-items").html(
				`<div class="text-muted" style="padding:20px 0;text-align:center;">${__("No data for this period")}</div>`);
			return;
		}
		const body = rows.map((r, i) => `
			<tr>
				<td>${i + 1}</td>
				<td>${frappe.utils.escape_html(r.label || "")}</td>
				<td class="fp-num">${r.qty}</td>
				<td class="fp-num">${this.fmt(r.value)}</td>
			</tr>`).join("");
		this.page.main.find(".fp-top-items").html(`
			<table>
				<thead><tr><th style="width:40px">#</th><th>${__("Item")}</th>
					<th class="fp-num" style="width:90px">${__("Qty")}</th>
					<th class="fp-num" style="width:130px">${__("Amount")}</th></tr></thead>
				<tbody>${body}</tbody>
			</table>`);
	}
}
