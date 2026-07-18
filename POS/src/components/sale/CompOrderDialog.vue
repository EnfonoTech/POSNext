<template>
	<Dialog
		:modelValue="modelValue"
		:options="{ title: __('Complimentary / Void order'), size: 'sm' }"
		@update:modelValue="$emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-xs text-gray-500">
					{{
						__(
							"This voids the order with no bill — no Sales Invoice is created. Stock for the served items is reversed and the comp awaits manager approval."
						)
					}}
				</p>
				<div class="space-y-1.5">
					<label class="text-sm font-semibold text-gray-800">
						{{ __("Reason") }} <span class="text-red-500">*</span>
					</label>
					<select
						v-model="reason"
						class="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
					>
						<option value="">{{ __("Select a reason…") }}</option>
						<option v-for="r in reasons" :key="r" :value="r">{{ __(r) }}</option>
					</select>
				</div>
				<div class="space-y-1.5">
					<label class="text-sm font-semibold text-gray-800">{{ __("Note") }}</label>
					<textarea
						v-model="reasonNote"
						rows="2"
						class="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
						:placeholder="__('Optional details')"
					/>
				</div>
			</div>
		</template>
		<template #actions>
			<button
				class="w-full rounded-md bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium py-2 disabled:opacity-50"
				:disabled="!reason"
				@click="confirm"
			>
				{{ __("Confirm comp / void") }}
			</button>
		</template>
	</Dialog>
</template>

<script setup>
// Complimentary / Void reason picker (Feature 1). Copies the ModifierDialog dialog
// shell: a v-model dialog that emits `confirm` with { reason, reason_note }. The
// confirm button stays disabled until a reason is chosen (a reason is mandatory —
// submit_complimentary_order also enforces it server-side). The reason list mirrors
// the POS Complimentary Order doctype `reason` field options.
import { Dialog } from "frappe-ui";
import { ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: Boolean, default: false },
});
const emit = defineEmits(["confirm", "update:modelValue"]);

// `__` (Frappe translation) delegates to the app-wide global when installed, else
// returns the source string so the dialog also renders standalone (unit test).
const __ = (msg, replace, ctx) =>
	typeof window !== "undefined" && typeof window.__ === "function"
		? window.__(msg, replace, ctx)
		: msg;

const reasons = [
	"Staff Meal",
	"Marketing / Promo",
	"Customer Complaint",
	"Wastage / Spillage",
	"Management",
	"Other",
];

const reason = ref("");
const reasonNote = ref("");

// Reset the form each time the dialog opens so a prior selection never leaks.
watch(
	() => props.modelValue,
	(open) => {
		if (open) {
			reason.value = "";
			reasonNote.value = "";
		}
	}
);

function confirm() {
	if (!reason.value) return;
	emit("confirm", { reason: reason.value, reason_note: reasonNote.value || null });
	emit("update:modelValue", false);
}
</script>
