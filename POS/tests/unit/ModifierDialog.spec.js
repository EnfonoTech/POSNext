// TDD (pre-implementation) — Dine-in on the main cart.
// Spec: .pipeline/spec.md  Implementation Step 1 "Extract ModifierDialog.vue" +
//        §"ModifierDialog.vue (new)".
//
// Subject: NEW shared component POS/src/components/sale/ModifierDialog.vue, lifted
// verbatim from Tables.vue (markup 176-224, logic 246-406). Contract:
//   props:  modelValue (open), itemCode, optional groups (pre-fetched)
//   emits:  confirm(selection), update:modelValue
//   selection shape: { group_name: label (Single) | [labels] (Multiple) },
//                    only groups with picks included.
//   validation (modValid): required→≥1 pick, min, max, Single→≤1; confirm disabled
//                    while invalid.
//   defaults: Single group's is_default option is pre-selected on open.
//
// EXPECTED PRE-IMPLEMENTATION RESULT: RED — the component file does not exist, so
// the import/mount fails. Post-implementation this should pass against a faithful
// extraction (explicit `vue` imports; Dialog renders #body-content and #actions).

import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

// Stub frappe-ui so the picker's Dialog renders its slots synchronously in jsdom.
vi.mock("frappe-ui", () => ({
	Dialog: {
		name: "Dialog",
		props: ["modelValue", "options"],
		template:
			'<div class="dialog-stub"><slot /><slot name="body-content" /><slot name="actions" /></div>',
	},
	Button: { name: "Button", template: "<button><slot /></button>" },
	createResource: () => ({ submit: vi.fn(), fetch: vi.fn(), data: null, loading: false }),
}));
// The picker resolves groups via the api wrapper when `groups` isn't supplied; we
// always pass `groups`, but mock the wrapper so no network path is taken.
vi.mock("@/utils/apiWrapper", () => ({ call: vi.fn(async () => []) }));
vi.mock("@/stores/posShift", () => ({
	usePOSShiftStore: () => ({ profileCurrency: "SAR", profileName: "Main POS" }),
}));

import ModifierDialog from "@/components/sale/ModifierDialog.vue";

function groupsRequiredSingleWithDefault() {
	return [
		{
			group_name: "Size",
			selection_type: "Single",
			is_required: 1,
			min: 0,
			max: 0,
			options: [
				{ label: "Regular", price_delta: 0, is_default: 1 },
				{ label: "Large", price_delta: 5 },
			],
		},
	];
}

function groupsRequiredSingleNoDefault() {
	return [
		{
			group_name: "Size",
			selection_type: "Single",
			is_required: 1,
			min: 0,
			max: 0,
			options: [
				{ label: "Regular", price_delta: 0 },
				{ label: "Large", price_delta: 5 },
			],
		},
	];
}

function groupsMultipleMaxTwo() {
	return [
		{
			group_name: "Extras",
			selection_type: "Multiple",
			is_required: 0,
			min: 0,
			max: 2,
			options: [
				{ label: "Extra Shot", price_delta: 3 },
				{ label: "Whipped Cream", price_delta: 2 },
				{ label: "Oat Milk", price_delta: 2.5 },
			],
		},
	];
}

function optionButton(wrapper, label) {
	return wrapper
		.findAll("button")
		.find((b) => b.text().includes(label) && b.text().length < 40);
}
function confirmButton(wrapper) {
	// The actions slot button — text like "Add to order". Fall back to a disabled-capable button.
	return (
		wrapper.findAll("button").find((b) => /add/i.test(b.text())) ||
		wrapper.findAll("button").at(-1)
	);
}

describe("ModifierDialog.vue — extracted shared picker", () => {
	it("pre-selects a Single group's is_default option on open", () => {
		const wrapper = mount(ModifierDialog, {
			props: { modelValue: true, itemCode: "ESPRESSO", groups: groupsRequiredSingleWithDefault() },
		});
		// required Single with a default -> valid immediately -> confirm enabled
		expect(confirmButton(wrapper).attributes("disabled")).toBeFalsy();
	});

	it("emits confirm with the default selection and closes the dialog", async () => {
		const wrapper = mount(ModifierDialog, {
			props: { modelValue: true, itemCode: "ESPRESSO", groups: groupsRequiredSingleWithDefault() },
		});
		await confirmButton(wrapper).trigger("click");
		const confirm = wrapper.emitted("confirm");
		expect(confirm).toBeTruthy();
		expect(confirm[0][0]).toEqual({ Size: "Regular" });
		expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toBe(false);
	});

	it("blocks confirm until a required group (no default) is satisfied", async () => {
		const wrapper = mount(ModifierDialog, {
			props: { modelValue: true, itemCode: "ESPRESSO", groups: groupsRequiredSingleNoDefault() },
		});
		expect(confirmButton(wrapper).attributes("disabled")).toBeDefined();
		await optionButton(wrapper, "Large").trigger("click");
		expect(confirmButton(wrapper).attributes("disabled")).toBeFalsy();
		await confirmButton(wrapper).trigger("click");
		expect(wrapper.emitted("confirm")[0][0]).toEqual({ Size: "Large" });
	});

	it("Single selection replaces (never accumulates) the picked label", async () => {
		const wrapper = mount(ModifierDialog, {
			props: { modelValue: true, itemCode: "ESPRESSO", groups: groupsRequiredSingleNoDefault() },
		});
		await optionButton(wrapper, "Regular").trigger("click");
		await optionButton(wrapper, "Large").trigger("click");
		await confirmButton(wrapper).trigger("click");
		expect(wrapper.emitted("confirm")[0][0]).toEqual({ Size: "Large" });
	});

	it("Multiple selection emits an array and enforces max_select", async () => {
		const wrapper = mount(ModifierDialog, {
			props: { modelValue: true, itemCode: "ESPRESSO", groups: groupsMultipleMaxTwo() },
		});
		await optionButton(wrapper, "Extra Shot").trigger("click");
		await optionButton(wrapper, "Whipped Cream").trigger("click");
		// two picks: valid
		expect(confirmButton(wrapper).attributes("disabled")).toBeFalsy();
		// third pick exceeds max_select=2 -> invalid, confirm blocked
		await optionButton(wrapper, "Oat Milk").trigger("click");
		expect(confirmButton(wrapper).attributes("disabled")).toBeDefined();
	});
});
