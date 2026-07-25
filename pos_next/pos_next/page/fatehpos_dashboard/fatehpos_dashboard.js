const FPD_CSS = `/* FatehPOS management dashboard — light/dark, design-system driven */
.fpd {
	color-scheme: light;
	--surface-1: #ffffff;
	--surface-2: #f7f7f5;
	--border: #e6e5e1;
	--text-primary: #0b0b0b;
	--text-secondary: #52514e;
	--text-muted: #86857f;
	--series-1: #2a78d6;   /* blue   */
	--series-2: #eb6834;   /* orange */
	--series-3: #1baf7a;   /* aqua   */
	--good: #087f5b;
	--bad: #c92a2a;
	--grid: #eeeeea;
	padding-bottom: 40px;
}
:root[data-theme="dark"] .fpd,
:root[data-theme="Dark"] .fpd {
	color-scheme: dark;
	--surface-1: #1a1a19;
	--surface-2: #212120;
	--border: #33332f;
	--text-primary: #ffffff;
	--text-secondary: #c3c2b7;
	--text-muted: #8f8e85;
	--series-1: #3987e5;
	--series-2: #d95926;
	--series-3: #199e70;
	--good: #37b24d;
	--bad: #ff6b6b;
	--grid: #2b2b28;
}

.fpd-filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 18px; }
.fpd-seg { display: inline-flex; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.fpd-seg button { border: 0; background: transparent; padding: 6px 12px; font-size: 12px; font-weight: 500;
	color: var(--text-secondary); cursor: pointer; }
.fpd-seg button + button { border-left: 1px solid var(--border); }
.fpd-seg button.active { background: var(--series-1); color: #fff; }

/* ---- stat tiles ---- */
.fpd-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }
.fpd-kpi { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; position: relative; overflow: hidden; }
.fpd-kpi-label { font-size: 11px; letter-spacing: .6px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }
.fpd-kpi-value { font-size: 26px; line-height: 1.15; font-weight: 700; color: var(--text-primary); margin-top: 6px;
	font-variant-numeric: tabular-nums; }
.fpd-kpi-sub { font-size: 12px; margin-top: 4px; color: var(--text-secondary); display: flex; align-items: center; gap: 5px; }
.fpd-up { color: var(--good); font-weight: 600; }
.fpd-down { color: var(--bad); font-weight: 600; }
.fpd-kpi-spark { position: absolute; right: 0; bottom: 0; opacity: .5; pointer-events: none; }

/* ---- cards ---- */
.fpd-grid { display: grid; gap: 12px; margin-bottom: 12px; }
.fpd-g-2-1 { grid-template-columns: 2fr 1fr; }
.fpd-g-1-1 { grid-template-columns: 1fr 1fr; }
@media (max-width: 992px) { .fpd-g-2-1, .fpd-g-1-1 { grid-template-columns: 1fr; } }
.fpd-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; min-width: 0; }
.fpd-card-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; gap: 8px; }
.fpd-card-title { font-size: 12px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: var(--text-secondary); }
.fpd-card-note { font-size: 11px; color: var(--text-muted); }
.fpd-empty { text-align: center; color: var(--text-muted); font-size: 13px; padding: 34px 0; }

/* ---- svg chart chrome ---- */
.fpd-svg { display: block; width: 100%; overflow: visible; }
.fpd-svg .grid line { stroke: var(--grid); stroke-width: 1; }
.fpd-svg .axis text { fill: var(--text-muted); font-size: 10px; }
.fpd-svg .axis-label { fill: var(--text-secondary); font-size: 11px; }
.fpd-svg .val-label { fill: var(--text-primary); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
.fpd-svg .hit { fill: transparent; cursor: pointer; }
.fpd-svg .crosshair { stroke: var(--text-muted); stroke-width: 1; stroke-dasharray: 3 3; }

/* ---- listbars (horizontal) ---- */
.fpd-rows { display: flex; flex-direction: column; gap: 10px; }
.fpd-row { display: grid; grid-template-columns: minmax(90px, 34%) 1fr auto; gap: 10px; align-items: center; font-size: 12px; }
.fpd-row-label { color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fpd-track { background: var(--surface-2); border-radius: 4px; height: 14px; position: relative; }
.fpd-bar { height: 14px; border-radius: 4px; }
.fpd-row-val { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.fpd-row-sub { color: var(--text-muted); font-weight: 400; }

/* ---- table ---- */
.fpd-table { width: 100%; font-size: 12px; border-collapse: collapse; }
.fpd-table th { text-align: left; color: var(--text-muted); font-weight: 600; text-transform: uppercase;
	font-size: 10px; letter-spacing: .5px; padding: 6px 6px; border-bottom: 1px solid var(--border); }
.fpd-table td { padding: 7px 6px; border-bottom: 1px solid var(--border); color: var(--text-primary); }
.fpd-table tr:last-child td { border-bottom: 0; }
.fpd-num { text-align: right; font-variant-numeric: tabular-nums; }
.fpd-link { background: none; border: 0; padding: 0; font-size: 11px; color: var(--series-1); cursor: pointer; }

/* ---- tooltip ---- */
.fpd-tip { position: fixed; z-index: 1050; pointer-events: none; background: var(--surface-1);
	border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 12px;
	color: var(--text-primary); box-shadow: 0 6px 18px rgba(0,0,0,.14); opacity: 0; transition: opacity .08s; }
.fpd-tip.on { opacity: 1; }
.fpd-tip b { font-variant-numeric: tabular-nums; }
.fpd-tip-key { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; }
`;

function fpd_inject_css() {
	if (document.getElementById("fpd-style")) return;
	const s = document.createElement("style");
	s.id = "fpd-style";
	s.textContent = FPD_CSS;
	document.head.appendChild(s);
}

frappe.pages["fatehpos-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("FatehPOS Dashboard"),
		single_column: true,
	});
	fpd_inject_css();
	new FatehPOSDashboard(page);
};

const FPD_RANGES = [
	{ key: "today", label: __("Today"), days: 0 },
	{ key: "7d", label: __("7 Days"), days: 6 },
	{ key: "30d", label: __("30 Days"), days: 29 },
	{ key: "90d", label: __("90 Days"), days: 89 },
];

class FatehPOSDashboard {
	constructor(page) {
		this.page = page;
		this.range = "30d";
		this.tables = {};
		this.make_filters();
		this.make_layout();
		this.tooltip = $('<div class="fpd-tip"></div>').appendTo(document.body);
		this.refresh();
		$(window).on("resize.fpd", frappe.utils.debounce(() => this.render(), 200));
	}

	// ---------------------------------------------------------------- filters
	make_filters() {
		this.company = this.page.add_field({
			fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
			default: frappe.defaults.get_user_default("Company"), change: () => this.refresh(),
		});
		this.cost_center = this.page.add_field({
			fieldname: "cost_center", label: __("Branch"), fieldtype: "Link", options: "Cost Center",
			get_query: () => ({ filters: { is_group: 0 } }), change: () => this.refresh(),
		});
		this.from_date = this.page.add_field({
			fieldname: "from_date", label: __("From"), fieldtype: "Date",
			change: () => { this.range = null; this.paint_seg(); this.refresh(); },
		});
		this.to_date = this.page.add_field({
			fieldname: "to_date", label: __("To"), fieldtype: "Date",
			change: () => { this.range = null; this.paint_seg(); this.refresh(); },
		});
		this.set_range("30d", true);
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	set_range(key, silent) {
		const r = FPD_RANGES.find((x) => x.key === key);
		if (!r) return;
		this.range = key;
		const today = frappe.datetime.get_today();
		this.from_date.set_input(frappe.datetime.add_days(today, -r.days));
		this.to_date.set_input(today);
		this.paint_seg();
		if (!silent) this.refresh();
	}

	paint_seg() {
		this.page.main.find(".fpd-seg button").each((_, b) => {
			$(b).toggleClass("active", $(b).data("key") === this.range);
		});
	}

	// ---------------------------------------------------------------- layout
	make_layout() {
		const seg = FPD_RANGES.map(
			(r) => `<button data-key="${r.key}">${r.label}</button>`
		).join("");
		this.page.main.html(`
			<div class="fpd">
				<div class="fpd-filters"><div class="fpd-seg">${seg}</div></div>
				<div class="fpd-kpis"></div>
				<div class="fpd-grid fpd-g-2-1">
					<div class="fpd-card" data-c="trend">
						<div class="fpd-card-head"><div class="fpd-card-title">${__("Sales Trend")}</div>
							<div class="fpd-card-note"></div></div>
						<div class="fpd-body"></div>
					</div>
					<div class="fpd-card" data-c="pay">
						<div class="fpd-card-head"><div class="fpd-card-title">${__("Payment Mix")}</div></div>
						<div class="fpd-body"></div>
					</div>
				</div>
				<div class="fpd-grid fpd-g-1-1">
					<div class="fpd-card" data-c="hour">
						<div class="fpd-card-head"><div class="fpd-card-title">${__("Sales by Hour")}</div>
							<div class="fpd-card-note"></div></div>
						<div class="fpd-body"></div>
					</div>
					<div class="fpd-card" data-c="branch">
						<div class="fpd-card-head"><div class="fpd-card-title">${__("Branch Performance")}</div></div>
						<div class="fpd-body"></div>
					</div>
				</div>
				<div class="fpd-grid fpd-g-1-1">
					<div class="fpd-card" data-c="items">
						<div class="fpd-card-head"><div class="fpd-card-title">${__("Top Items")}</div>
							<button class="fpd-link" data-toggle="items">${__("Table view")}</button></div>
						<div class="fpd-body"></div>
					</div>
					<div class="fpd-card" data-c="cashier">
						<div class="fpd-card-head"><div class="fpd-card-title">${__("Cashier Performance")}</div></div>
						<div class="fpd-body"></div>
					</div>
				</div>
			</div>
		`);
		this.paint_seg();
		this.page.main.on("click", ".fpd-seg button", (e) => this.set_range($(e.currentTarget).data("key")));
		this.page.main.on("click", "[data-toggle]", (e) => {
			const k = $(e.currentTarget).data("toggle");
			this.tables[k] = !this.tables[k];
			$(e.currentTarget).text(this.tables[k] ? __("Chart view") : __("Table view"));
			this.render();
		});
	}

	// ---------------------------------------------------------------- data
	refresh() {
		frappe.call({
			method: "pos_next.api.dashboard.get_dashboard_data",
			args: {
				from_date: this.from_date.get_value(),
				to_date: this.to_date.get_value(),
				company: this.company.get_value(),
				cost_center: this.cost_center.get_value(),
			},
			callback: (r) => {
				if (!r.message) return;
				this.data = r.message;
				this.render();
			},
		});
	}

	fmt(v) { return format_currency(v, this.data.currency); }
	short(v) {
		const n = Math.abs(v);
		if (n >= 1e6) return (v / 1e6).toFixed(1) + "M";
		if (n >= 1e3) return (v / 1e3).toFixed(1) + "k";
		return Math.round(v).toString();
	}
	body(name) { return this.page.main.find(`[data-c="${name}"] .fpd-body`); }
	note(name, txt) { this.page.main.find(`[data-c="${name}"] .fpd-card-note`).text(txt || ""); }

	render() {
		if (!this.data) return;
		this.render_kpis();
		this.render_trend();
		this.render_payments();
		this.render_hourly();
		this.render_branches();
		this.render_items();
		this.render_cashiers();
	}

	// ---------------------------------------------------------------- KPIs
	render_kpis() {
		const k = this.data.kpi;
		const spark = this.sparkline(this.data.trend.map((t) => t.value));
		const delta = (v) => {
			if (v === null || v === undefined)
				return `<span class="text-muted">${__("no prior data")}</span>`;
			const cls = v > 0 ? "fpd-up" : v < 0 ? "fpd-down" : "";
			const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "▬";
			return `<span class="${cls}">${arrow} ${Math.abs(v)}%</span> <span class="text-muted">${__("vs prev")}</span>`;
		};
		const peak = (this.data.hourly || []).reduce((a, b) => (b.value > (a?.value || 0) ? b : a), null);
		const tile = (label, value, sub, sparkSvg) => `
			<div class="fpd-kpi">
				<div class="fpd-kpi-label">${label}</div>
				<div class="fpd-kpi-value">${value}</div>
				<div class="fpd-kpi-sub">${sub || ""}</div>
				${sparkSvg ? `<div class="fpd-kpi-spark">${sparkSvg}</div>` : ""}
			</div>`;
		this.body_kpis = this.page.main.find(".fpd-kpis").html([
			tile(__("Total Sales"), this.fmt(k.sales), delta(k.sales_change), spark),
			tile(__("Invoices"), k.invoices, delta(k.invoices_change)),
			tile(__("Avg Ticket"), this.fmt(k.avg_ticket),
				`<span class="text-muted">${__("{0} items sold", [k.qty])}</span>`),
			tile(__("VAT Collected"), this.fmt(k.vat),
				`<span class="text-muted">${__("Net")} ${this.fmt(k.net)}</span>`),
			tile(__("Peak Hour"), peak ? peak.label : "—",
				peak ? `<span class="text-muted">${this.fmt(peak.value)}</span>` : ""),
		].join(""));
	}

	sparkline(values) {
		if (!values || values.length < 2) return "";
		const w = 110, h = 34, max = Math.max(...values), min = Math.min(...values);
		const span = max - min || 1;
		const pts = values.map((v, i) => [
			(i / (values.length - 1)) * w,
			h - 4 - ((v - min) / span) * (h - 10),
		]);
		const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
		const area = `${d} L${w},${h} L0,${h} Z`;
		return `<svg width="${w}" height="${h}" aria-hidden="true">
			<path d="${area}" fill="var(--series-1)" opacity=".10"></path>
			<path d="${d}" fill="none" stroke="var(--series-1)" stroke-width="2"
				stroke-linecap="round" stroke-linejoin="round"></path></svg>`;
	}

	// ---------------------------------------------------------------- tooltip
	tip_show(evt, html) {
		this.tooltip.html(html).addClass("on");
		const pad = 14, tw = this.tooltip.outerWidth(), th = this.tooltip.outerHeight();
		let x = evt.clientX + pad, y = evt.clientY - th - 8;
		if (x + tw > window.innerWidth - 8) x = evt.clientX - tw - pad;
		if (y < 8) y = evt.clientY + pad;
		this.tooltip.css({ left: x + "px", top: y + "px" });
	}
	tip_hide() { this.tooltip.removeClass("on"); }

	// ---------------------------------------------------------------- trend
	render_trend() {
		const el = this.body("trend"), rows = this.data.trend;
		this.note("trend", `${this.data.from_date} → ${this.data.to_date}`);
		if (!rows.length) return el.html(`<div class="fpd-empty">${__("No sales in this period")}</div>`);
		if (rows.length === 1) {
			return el.html(`<div style="padding:26px 0;text-align:center;">
				<div class="fpd-kpi-value">${this.fmt(rows[0].value)}</div>
				<div class="text-muted" style="font-size:12px;">${rows[0].label}</div></div>`);
		}
		const W = Math.max(el.width() || 600, 320), H = 260;
		const m = { t: 12, r: 14, b: 26, l: 52 };
		const iw = W - m.l - m.r, ih = H - m.t - m.b;
		const max = Math.max(...rows.map((r) => r.value)) || 1;
		const nice = this.nice_max(max);
		const X = (i) => m.l + (rows.length === 1 ? iw / 2 : (i / (rows.length - 1)) * iw);
		const Y = (v) => m.t + ih - (v / nice) * ih;

		const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => nice * f);
		const grid = ticks.map((t) =>
			`<line x1="${m.l}" x2="${W - m.r}" y1="${Y(t).toFixed(1)}" y2="${Y(t).toFixed(1)}"></line>`).join("");
		const ylab = ticks.map((t) =>
			`<text x="${m.l - 8}" y="${(Y(t) + 3).toFixed(1)}" text-anchor="end">${this.short(t)}</text>`).join("");
		const line = rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(r.value).toFixed(1)}`).join(" ");
		const area = `${line} L${X(rows.length - 1).toFixed(1)},${m.t + ih} L${X(0).toFixed(1)},${m.t + ih} Z`;

		const step = Math.ceil(rows.length / Math.max(2, Math.floor(iw / 90)));
		const xlab = rows.map((r, i) =>
			i % step === 0 || i === rows.length - 1
				? `<text x="${X(i).toFixed(1)}" y="${H - 6}" text-anchor="middle">${r.label.slice(5)}</text>` : "").join("");

		const dots = rows.length <= 40
			? rows.map((r, i) => `<circle cx="${X(i).toFixed(1)}" cy="${Y(r.value).toFixed(1)}" r="3.5"
				fill="var(--surface-1)" stroke="var(--series-1)" stroke-width="2"></circle>`).join("") : "";

		const hits = rows.map((r, i) => `<rect class="hit" x="${(X(i) - iw / rows.length / 2).toFixed(1)}"
			y="${m.t}" width="${(iw / rows.length).toFixed(1)}" height="${ih}" data-i="${i}"></rect>`).join("");

		el.html(`<svg class="fpd-svg" viewBox="0 0 ${W} ${H}" height="${H}">
			<g class="grid">${grid}</g>
			<g class="axis">${ylab}${xlab}</g>
			<path d="${area}" fill="var(--series-1)" opacity=".10"></path>
			<path d="${line}" fill="none" stroke="var(--series-1)" stroke-width="2"
				stroke-linecap="round" stroke-linejoin="round"></path>
			${dots}
			<line class="crosshair" style="display:none" y1="${m.t}" y2="${m.t + ih}"></line>
			${hits}
		</svg>`);

		const svg = el.find("svg")[0], ch = el.find(".crosshair");
		el.find(".hit").on("mousemove", (e) => {
			const i = +$(e.currentTarget).data("i"), r = rows[i];
			ch.attr({ x1: X(i).toFixed(1), x2: X(i).toFixed(1) }).show();
			this.tip_show(e, `<div>${r.label}</div><b>${this.fmt(r.value)}</b>`);
		}).on("mouseleave", () => { ch.hide(); this.tip_hide(); });
		void svg;
	}

	nice_max(v) {
		if (v <= 0) return 1;
		const p = Math.pow(10, Math.floor(Math.log10(v)));
		return Math.ceil(v / p) * p;
	}

	// ---------------------------------------------------------------- bars
	listbars(el, rows, opts = {}) {
		if (!rows.length) return el.html(`<div class="fpd-empty">${__("No data")}</div>`);
		const max = Math.max(...rows.map((r) => r.value)) || 1;
		const color = opts.color || "var(--series-1)";
		el.html(`<div class="fpd-rows">${rows.map((r, i) => {
			const pctw = Math.max(2, (r.value / max) * 100);
			const c = opts.colors ? opts.colors[i % opts.colors.length] : color;
			return `<div class="fpd-row" data-i="${i}">
				<div class="fpd-row-label" title="${frappe.utils.escape_html(r.label || "")}">${frappe.utils.escape_html(r.label || "")}</div>
				<div class="fpd-track"><div class="fpd-bar" style="width:${pctw}%;background:${c}"></div></div>
				<div class="fpd-row-val">${this.fmt(r.value)}${
					r.sub ? ` <span class="fpd-row-sub">${r.sub}</span>` : ""}</div>
			</div>`;
		}).join("")}</div>`);
		el.find(".fpd-row").on("mousemove", (e) => {
			const r = rows[+$(e.currentTarget).data("i")];
			this.tip_show(e, `<div>${frappe.utils.escape_html(r.label || "")}</div><b>${this.fmt(r.value)}</b>${
				r.tip ? `<div class="text-muted">${r.tip}</div>` : ""}`);
		}).on("mouseleave", () => this.tip_hide());
	}

	render_payments() {
		const rows = (this.data.payments || []).map((p, i) => ({ ...p, _i: i }));
		const total = rows.reduce((a, b) => a + b.value, 0) || 1;
		const colors = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
		this.listbars(this.body("pay"), rows.map((r) => ({
			label: r.label, value: r.value,
			sub: `${((r.value / total) * 100).toFixed(0)}%`,
		})), { colors });
	}

	render_branches() {
		const rows = this.data.branches || [];
		const total = rows.reduce((a, b) => a + b.value, 0) || 1;
		this.listbars(this.body("branch"), rows.map((r) => ({
			label: r.label, value: r.value, sub: `${((r.value / total) * 100).toFixed(0)}%`,
		})));
	}

	render_cashiers() {
		const rows = this.data.cashiers || [];
		this.listbars(this.body("cashier"), rows.map((r) => ({
			label: (r.label || "").split("@")[0], value: r.value,
			sub: `${r.invoices} ${__("inv")}`, tip: `${r.invoices} ${__("invoices")}`,
		})), { color: "var(--series-3)" });
	}

	render_items() {
		const el = this.body("items"), rows = this.data.items || [];
		if (this.tables.items) {
			if (!rows.length) return el.html(`<div class="fpd-empty">${__("No data")}</div>`);
			return el.html(`<table class="fpd-table"><thead><tr>
				<th>#</th><th>${__("Item")}</th><th class="fpd-num">${__("Qty")}</th><th class="fpd-num">${__("Amount")}</th>
				</tr></thead><tbody>${rows.map((r, i) => `<tr><td>${i + 1}</td>
					<td>${frappe.utils.escape_html(r.label || "")}</td>
					<td class="fpd-num">${r.qty}</td><td class="fpd-num">${this.fmt(r.value)}</td></tr>`).join("")}
				</tbody></table>`);
		}
		this.listbars(el, rows.map((r) => ({
			label: r.label, value: r.value, sub: `×${r.qty}`, tip: `${__("Qty")}: ${r.qty}`,
		})), { color: "var(--series-2)" });
	}

	// ---------------------------------------------------------------- hourly
	render_hourly() {
		const el = this.body("hour"), rows = this.data.hourly || [];
		if (!rows.length) return el.html(`<div class="fpd-empty">${__("No data")}</div>`);
		const peak = rows.reduce((a, b) => (b.value > a.value ? b : a), rows[0]);
		this.note("hour", __("Peak {0}", [peak.label]));
		const W = Math.max(el.width() || 420, 300), H = 220;
		const m = { t: 12, r: 10, b: 26, l: 46 };
		const iw = W - m.l - m.r, ih = H - m.t - m.b;
		const nice = this.nice_max(Math.max(...rows.map((r) => r.value)));
		const bw = Math.max(6, Math.min(34, (iw / rows.length) - 6));
		const X = (i) => m.l + (i + 0.5) * (iw / rows.length) - bw / 2;
		const Y = (v) => m.t + ih - (v / nice) * ih;
		const ticks = [0, 0.5, 1].map((f) => nice * f);
		const grid = ticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(t).toFixed(1)}" y2="${Y(t).toFixed(1)}"></line>`).join("");
		const ylab = ticks.map((t) => `<text x="${m.l - 8}" y="${(Y(t) + 3).toFixed(1)}" text-anchor="end">${this.short(t)}</text>`).join("");
		const step = Math.ceil(rows.length / Math.max(2, Math.floor(iw / 60)));
		const bars = rows.map((r, i) => {
			const h = Math.max(2, m.t + ih - Y(r.value));
			const isPeak = r.label === peak.label;
			return `<rect class="bar" x="${X(i).toFixed(1)}" y="${Y(r.value).toFixed(1)}" width="${bw.toFixed(1)}"
				height="${h.toFixed(1)}" rx="4" fill="${isPeak ? "var(--series-2)" : "var(--series-1)"}"></rect>
				<rect class="hit" x="${X(i).toFixed(1)}" y="${m.t}" width="${bw.toFixed(1)}" height="${ih}" data-i="${i}"></rect>`;
		}).join("");
		const xlab = rows.map((r, i) => i % step === 0
			? `<text x="${(X(i) + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle">${r.label.slice(0, 2)}</text>` : "").join("");
		el.html(`<svg class="fpd-svg" viewBox="0 0 ${W} ${H}" height="${H}">
			<g class="grid">${grid}</g><g class="axis">${ylab}${xlab}</g>${bars}</svg>`);
		el.find(".hit").on("mousemove", (e) => {
			const r = rows[+$(e.currentTarget).data("i")];
			this.tip_show(e, `<div>${r.label}</div><b>${this.fmt(r.value)}</b>`);
		}).on("mouseleave", () => this.tip_hide());
	}
}
