/**
 * Regression guard: every print path must render the POS Profile's own print
 * format.
 *
 * On 2026-08-17 enabling POS Settings.silent_print swapped the branch receipt
 * (logo, Arabic, ZATCA QR) for the built-in "POS Next Receipt" on 236 live
 * invoices. Cause: the silent path called DEFAULT_PRINT_FORMAT while only
 * printInvoiceByName() resolved the profile. These tests pin the format that
 * each entry point asks the server for.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
const qzPrintHTML = vi.fn();

vi.mock("@/utils/apiWrapper", () => ({ call: (...a) => call(...a) }));
vi.mock("@/utils/qzTray", () => ({ printHTML: (...a) => qzPrintHTML(...a) }));
vi.mock("@/utils/logger", () => ({
	logger: { create: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }) },
}));
vi.mock("@/utils/offline/offlineReceiptCache", () => ({ getOfflineReceiptPayload: vi.fn() }));
vi.mock("@/utils/offline/sync", () => ({ getOfflineInvoiceByOfflineId: vi.fn() }));
vi.mock("@/utils/offline/workerClient", () => ({ offlineWorker: { flagPrinted: vi.fn() } }));

globalThis.__ = (s) => s;

const BRANCH_FORMAT = "Malabar Chillis Receipt";
const DEFAULT_FORMAT = "POS Next Receipt";
const PROFILE = "Mazroohiya POS";
const INVOICE = "MAZ-2026-00076";

let mod;

/** The print_format the code asked printview to render. */
function requestedFormat() {
	const hit = call.mock.calls.find(([m]) => m === "frappe.www.printview.get_html_and_style");
	return hit?.[1]?.print_format;
}

beforeEach(async () => {
	vi.resetModules();
	call.mockReset();
	qzPrintHTML.mockReset();

	call.mockImplementation(async (method, args) => {
		if (method === "frappe.client.get" && args.doctype === "POS Profile") {
			return { name: args.name, print_format: BRANCH_FORMAT, letter_head: null };
		}
		if (method === "frappe.www.printview.get_html_and_style") {
			return { html: `<div>${args.print_format}</div>`, style: "" };
		}
		if (method === "pos_next.api.invoices.get_invoice") {
			return { name: INVOICE, doctype: "Sales Invoice", pos_profile: PROFILE, items: [{}] };
		}
		return null;
	});

	mod = await import("@/utils/printInvoice");
});

describe("silentPrintInvoice", () => {
	it("renders the POS Profile format, not the built-in default", async () => {
		await mod.silentPrintInvoice(INVOICE, null, PROFILE);
		expect(requestedFormat()).toBe(BRANCH_FORMAT);
	});

	it("still honours an explicitly passed format", async () => {
		await mod.silentPrintInvoice(INVOICE, "RMS B2B Tax Invoice", PROFILE);
		expect(requestedFormat()).toBe("RMS B2B Tax Invoice");
	});

	it("falls back to the default only when there is no profile at all", async () => {
		await mod.silentPrintInvoice(INVOICE, null, null);
		expect(requestedFormat()).toBe(DEFAULT_FORMAT);
	});
});

describe("printWithSilentFallback", () => {
	const invoice = { name: INVOICE, doctype: "Sales Invoice", pos_profile: PROFILE, items: [{}] };

	it("uses the branch format on the silent path", async () => {
		const res = await mod.printWithSilentFallback({ ...invoice });
		expect(res).toEqual({ method: "silent", success: true });
		expect(requestedFormat()).toBe(BRANCH_FORMAT);
	});

	it("uses the SAME format when QZ Tray is down and it falls back", async () => {
		// The real regression: which receipt the customer got depended on whether
		// QZ Tray happened to be connected.
		qzPrintHTML.mockRejectedValue(new Error("QZ Tray not connected"));
		await mod.printWithSilentFallback({ ...invoice });
		const formats = call.mock.calls
			.filter(([m]) => m === "frappe.www.printview.get_html_and_style")
			.map(([, a]) => a.print_format);
		expect(formats.length).toBeGreaterThan(0);
		expect(new Set(formats)).toEqual(new Set([BRANCH_FORMAT]));
	});

	it("resolves the profile once, not per print attempt", async () => {
		await mod.printWithSilentFallback({ ...invoice });
		const lookups = call.mock.calls.filter(
			([m, a]) => m === "frappe.client.get" && a.doctype === "POS Profile"
		);
		expect(lookups).toHaveLength(1);
	});
});

describe("printInvoice", () => {
	it("resolves the format from the invoice's own POS Profile", async () => {
		await mod.printInvoice({
			name: INVOICE,
			doctype: "Sales Invoice",
			pos_profile: PROFILE,
			items: [{}],
		});
		expect(requestedFormat()).toBe(BRANCH_FORMAT);
	});
});

describe("resolvePrintSettings", () => {
	it("caches per profile and clearPrintSettingsCache empties it", async () => {
		await mod.resolvePrintSettings(PROFILE, null, null);
		await mod.resolvePrintSettings(PROFILE, null, null);
		const lookups = () =>
			call.mock.calls.filter(([m, a]) => m === "frappe.client.get" && a.doctype === "POS Profile");
		expect(lookups()).toHaveLength(1);

		mod.clearPrintSettingsCache();
		await mod.resolvePrintSettings(PROFILE, null, null);
		expect(lookups()).toHaveLength(2);
	});

	it("returns the default when the profile lookup throws", async () => {
		call.mockImplementation(async (method) => {
			if (method === "frappe.client.get") throw new Error("network");
			return null;
		});
		const out = await mod.resolvePrintSettings(PROFILE, null, null);
		expect(out.printFormat).toBe(DEFAULT_FORMAT);
	});
});
