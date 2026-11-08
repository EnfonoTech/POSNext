// Numo look for the POS desk forms. Loaded by app_include_js (sites with pos_next only).
// Adds a status banner, a setup checklist (POS Profile), a sticky section nav and section
// icons; numo_pos_forms.css does the rest. Handlers stack on top of the upstream form
// scripts and never change data. Every injection is removed first, so a refresh never
// duplicates it.

(() => {
	const BASE = "/assets/pos_next/pos/";
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));

	const ICON = {
		users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
		pay: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
		gear: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
		filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
		print: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
		book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
		tag: '<path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1"/>',
		wallet: '<path d="M20 12V8H6a2 2 0 0 1 0-4h12v4"/><path d="M4 6v12a2 2 0 0 0 2 2h14v-4"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
		eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
		cart: '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>',
		truck: '<path d="M1 3h15v13H1z"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
		shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
		globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
		receipt: '<path d="M4 2v20l3-2 3 2 3-2 3 2 3-2 3 2V2l-3 2-3-2-3 2-3-2-3 2z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
		cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
		layers: '<path d="m12 2 10 5-10 5L2 7l10-5z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
		check: '<path d="M20 6 9 17l-5-5"/>',
		alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
		open: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/>',
	};
	const svg = (name) =>
		`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name] || ICON.layers}</svg>`;

	// Section label keyword -> icon. First match wins.
	const SECTION_ICONS = [
		[/user|staff|cashier/i, "users"],
		[/payment|mode|tender/i, "pay"],
		[/print|receipt/i, "print"],
		[/filter|group/i, "filter"],
		[/dimension|accounting|account/i, "book"],
		[/pricing|price|discount|offer/i, "tag"],
		[/wallet|loyalty/i, "wallet"],
		[/display|view/i, "eye"],
		[/delivery/i, "truck"],
		[/security|barcode/i, "shield"],
		[/locali|language/i, "globe"],
		[/expense|cash/i, "cash"],
		[/invoice|sale|order|operation|customer/i, "cart"],
		[/detail|summary/i, "receipt"],
		[/config|setting|general|advanced|misc|compliance/i, "gear"],
	];

	function section_icon(label) {
		const hit = SECTION_ICONS.find(([re]) => re.test(label || ""));
		return hit ? hit[1] : "layers";
	}

	function reset(frm) {
		const $w = $(frm.wrapper);
		$w.addClass("numo-pos-form");
		$w.find(".numo-hero, .numo-secnav, .numo-sec-icon").remove();
		return $w;
	}

	function decorate_sections(frm, $w) {
		const sections = [];
		$w.find(".form-layout .form-page > .form-section, .form-layout .tab-pane > .form-section").each(function (i) {
			const $sec = $(this);
			const $head = $sec.find("> .section-head").first();
			const label = $head.text().trim();
			if (!label || $sec.hasClass("hide-control") || !$sec.is(":visible")) return;
			$head.prepend(`<span class="numo-sec-icon">${svg(section_icon(label))}</span>`);
			sections.push({ label, el: this, i });
		});
		return sections;
	}

	function render_secnav(frm, $w, sections) {
		if (sections.length < 3) return;
		const $nav = $(
			`<nav class="numo-secnav" aria-label="${esc(__("Sections"))}">${sections
				.map((s, n) => `<button type="button" data-n="${n}">${esc(__(s.label))}</button>`)
				.join("")}</nav>`,
		);
		$nav.on("click", "button", function () {
			const s = sections[$(this).data("n")];
			const $head = $(s.el).find("> .section-head");
			if ($(s.el).find("> .section-body").is(":hidden")) $head.trigger("click");
			s.el.scrollIntoView({ behavior: "smooth", block: "start" });
			$nav.find("button").removeClass("is-active");
			$(this).addClass("is-active");
		});
		$w.find(".form-layout .form-tabs-list, .form-layout .form-page").first().before($nav);
	}

	function fact(label, value, empty_text) {
		const has = value != null && value !== "";
		return `<div class="numo-fact"><div class="numo-fact-label">${esc(label)}</div>
			<div class="numo-fact-value ${has ? "" : "is-empty"}" title="${esc(has ? value : "")}">${esc(
				has ? value : empty_text || __("Not set"),
			)}</div></div>`;
	}

	function hero(title, subtitle, pill, actions, body) {
		return `<div class="numo-hero">
			<div class="numo-hero-mark"><img src="${BASE}numo-mark.webp" alt=""></div>
			<div class="numo-hero-title"><h3>${esc(title)}</h3><p>${esc(subtitle)}</p></div>
			${pill}
			<div class="numo-hero-actions">${actions}</div>
			${body}
		</div>`;
	}

	const pill = (on, on_text, off_text, warn) =>
		`<span class="numo-pill ${warn ? "is-warn" : on ? "is-on" : "is-off"}">${esc(on ? on_text : off_text)}</span>`;

	const open_pos_btn = () =>
		`<a class="numo-btn" href="/pos" target="_blank" rel="noopener">${svg("open")}${esc(__("Open POS"))}</a>`;

	function place_hero(frm, $w, html) {
		const $hero = $(html);
		$w.find(".form-layout").first().prepend($hero);
		return $hero;
	}

	// ---------- POS Profile ----------
	function profile_checks(doc) {
		const payments = doc.payments || [];
		return [
			{ ok: !!doc.warehouse, label: __("Warehouse"), field: "warehouse" },
			{ ok: !!doc.selling_price_list, label: __("Price List"), field: "selling_price_list" },
			{ ok: payments.length > 0, label: __("Payment method"), field: "payments" },
			{ ok: payments.some((p) => p.default), label: __("Default payment"), field: "payments" },
			{ ok: (doc.applicable_for_users || []).length > 0, label: __("Cashier"), field: "applicable_for_users" },
			{ ok: !!doc.customer, label: __("Walk-in customer"), field: "customer" },
			{ ok: !!doc.write_off_account && !!doc.write_off_cost_center, label: __("Write off"), field: "write_off_account" },
		];
	}

	function render_profile(frm) {
		const $w = reset(frm);
		if (frm.is_new()) {
			decorate_sections(frm, $w);
			return;
		}
		const d = frm.doc;
		const checks = profile_checks(d);
		const todo = checks.filter((c) => !c.ok).length;
		const payments = (d.payments || []).map((p) => p.mode_of_payment).filter(Boolean);
		const status = d.disabled
			? pill(false, "", __("Disabled"))
			: todo
				? pill(false, "", __("{0} to set up", [todo]), true)
				: pill(true, __("Ready to sell"), "");
		const body = `<div class="numo-facts">
				${fact(__("Company"), d.company)}
				${fact(__("Warehouse"), d.warehouse)}
				${fact(__("Price List"), d.selling_price_list)}
				${fact(__("Payments"), payments.join(", "))}
				${fact(__("Cashiers"), (d.applicable_for_users || []).length || "")}
				${fact(__("Tax Template"), d.taxes_and_charges, __("None (tax free)"))}
			</div>
			<div class="numo-checklist">
				<span class="numo-checklist-title">${esc(__("Setup"))}</span>
				${checks
					.map(
						(c) =>
							`<span class="numo-check ${c.ok ? "is-done" : "is-todo"}" data-field="${esc(c.field)}" role="button" tabindex="0">${svg(
								c.ok ? "check" : "alert",
							)}${esc(c.label)}</span>`,
					)
					.join("")}
			</div>`;
		const $hero = place_hero(
			frm,
			$w,
			hero(d.name, __("POS Profile · {0}", [d.company || ""]), status, open_pos_btn(), body),
		);
		$hero.on("click keydown", ".numo-check.is-todo", function (e) {
			if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
			frm.scroll_to_field($(this).data("field"));
		});
		render_secnav(frm, $w, decorate_sections(frm, $w));
	}

	// ---------- POS Settings ----------
	function render_settings(frm) {
		const $w = reset(frm);
		const d = frm.doc;
		const checks = frm.meta.fields.filter((f) => f.fieldtype === "Check" && !f.hidden && f.fieldname !== "enabled");
		const on = checks.filter((f) => d[f.fieldname]).length;
		const highlights = [
			["allow_return", __("Returns")],
			["allow_credit_sale", __("Credit sales")],
			["enable_loyalty_program", __("Loyalty")],
			["tax_inclusive", __("Prices include tax")],
			["silent_print", __("Silent print")],
		]
			.filter(([f]) => frappe.meta.has_field(frm.doctype, f))
			.map(([f, label]) => fact(label, d[f] ? __("On") : __("Off")))
			.join("");
		const body = `<div class="numo-facts">
				${fact(__("POS Profile"), d.pos_profile)}
				${fact(__("Options on"), __("{0} of {1}", [on, checks.length]))}
				${highlights}
			</div>`;
		const actions =
			(d.pos_profile
				? `<a class="numo-btn is-ghost" href="/app/pos-profile/${encodeURIComponent(d.pos_profile)}">${svg("layers")}${esc(
						__("POS Profile"),
					)}</a>`
				: "") + open_pos_btn();
		if (!frm.is_new()) {
			place_hero(
				frm,
				$w,
				hero(
					d.pos_profile || d.name,
					__("POS Settings"),
					pill(!!d.enabled, __("Enabled"), __("Disabled")),
					actions,
					body,
				),
			);
		}
		render_secnav(frm, $w, decorate_sections(frm, $w));
	}

	// ---------- shifts + branch: cards, icons, nav ----------
	function render_plain(frm) {
		const $w = reset(frm);
		render_secnav(frm, $w, decorate_sections(frm, $w));
	}

	const later = (fn) => (frm) => setTimeout(() => fn(frm), 0);

	frappe.ui.form.on("POS Profile", {
		refresh: later(render_profile),
		after_save: later(render_profile),
		payments_remove: later(render_profile),
		applicable_for_users_remove: later(render_profile),
	});
	for (const f of ["warehouse", "selling_price_list", "customer", "write_off_account", "write_off_cost_center", "taxes_and_charges", "disabled"]) {
		frappe.ui.form.on("POS Profile", f, later(render_profile));
	}
	frappe.ui.form.on("POS Payment Method", { mode_of_payment: (frm) => render_profile(frm), default: (frm) => render_profile(frm) });
	frappe.ui.form.on("POS Profile User", { user: (frm) => render_profile(frm) });

	frappe.ui.form.on("POS Settings", { refresh: later(render_settings), after_save: later(render_settings) });
	for (const dt of ["POS Opening Shift", "POS Closing Shift", "Branch Configuration"]) {
		frappe.ui.form.on(dt, { refresh: later(render_plain) });
	}
})();
