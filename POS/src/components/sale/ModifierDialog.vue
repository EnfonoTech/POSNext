<template>
	<Dialog
		:modelValue="modelValue"
		:options="{ title: __('Choose options'), size: 'sm' }"
		@update:modelValue="$emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="modGroups.length" class="space-y-4">
				<div v-if="itemCode" class="text-sm font-medium text-gray-900">{{ itemCode }}</div>
				<div v-for="g in modGroups" :key="g.group_name" class="space-y-1.5">
					<div class="flex items-center justify-between">
						<span class="text-sm font-semibold text-gray-800">
							{{ g.group_name }}
							<span v-if="g.is_required" class="text-red-500">*</span>
						</span>
						<span class="text-xs text-gray-400">
							{{ g.selection_type === "Single" ? __("pick one") : __("pick any") }}
						</span>
					</div>
					<div class="grid grid-cols-2 gap-2">
						<button
							v-for="o in g.options"
							:key="o.label"
							class="flex items-center justify-between rounded-lg border px-3 py-2 text-sm transition"
							:class="
								isPicked(g, o.label)
									? 'border-blue-500 bg-blue-50 text-blue-700'
									: 'border-gray-200 hover:border-blue-300 text-gray-700'
							"
							@click="toggleOption(g, o.label)"
						>
							<span>{{ o.label }}</span>
							<span v-if="Number(o.price_delta) > 0" class="text-xs text-gray-500">
								+{{ Number(o.price_delta).toFixed(2) }}
							</span>
						</button>
					</div>
				</div>
				<div class="flex items-center justify-between border-t pt-3 text-sm">
					<span class="text-gray-500">{{ __("Modifiers") }}</span>
					<span class="font-medium">
						+{{ modDeltaTotal.toFixed(2) }} {{ shiftStore.profileCurrency || "SAR" }}
					</span>
				</div>
			</div>
		</template>
		<template #actions>
			<button
				class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 disabled:opacity-50"
				:disabled="!modValid"
				@click="confirmModifiers"
			>
				{{ __("Add to order") }}
			</button>
		</template>
	</Dialog>
</template>

<script setup>
// Shared modifier picker, extracted verbatim from Tables.vue (markup 176-224,
// logic 246-406) so the main dine-in cart and the (legacy) tables floor use one
// picker. It renders a v-model dialog, resolves the item's modifier groups (from
// the `groups` prop when supplied, else via get_item_modifiers), pre-selects Single
// group defaults, validates required/min/max/single, and emits the chosen selection
// object { group_name: label (Single) | [labels] (Multiple) } — only groups picked.
import { Dialog } from "frappe-ui";
import { call } from "@/utils/apiWrapper";
import { usePOSShiftStore } from "@/stores/posShift";
import { computed, reactive, ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	itemCode: { type: String, default: "" },
	// Optional pre-fetched groups; when null the picker fetches them on open.
	groups: { type: Array, default: null },
});
const emit = defineEmits(["confirm", "update:modelValue"]);

// `__` (Frappe translation) is installed app-wide in production via the
// utils/translation Vue plugin (app.config.globalProperties.__). Bind it locally,
// delegating to the global, so this extracted component also renders standalone
// (e.g. mounted directly in a unit test) without the plugin being installed.
const __ = (msg, replace, ctx) =>
	typeof window !== "undefined" && typeof window.__ === "function"
		? window.__(msg, replace, ctx)
		: msg;

const shiftStore = usePOSShiftStore();

const modGroups = ref([]); // resolved groups (from prop or get_item_modifiers)
const modSel = reactive({}); // group_name -> label (Single) | [labels] (Multiple)

const modDeltaTotal = computed(() => {
	let d = 0;
	for (const g of modGroups.value) {
		const picked = pickedLabels(g);
		for (const o of g.options) {
			if (picked.includes(o.label)) d += Number(o.price_delta) || 0;
		}
	}
	return d;
});

function pickedLabels(g) {
	const v = modSel[g.group_name];
	if (v == null || v === "") return [];
	return Array.isArray(v) ? v : [v];
}

const modValid = computed(() =>
	modGroups.value.every((g) => {
		const n = pickedLabels(g).length;
		if (g.is_required && n < 1) return false;
		if (n > 0 && g.min && n < g.min) return false;
		if (g.max && n > g.max) return false;
		if (g.selection_type === "Single" && n > 1) return false;
		return true;
	})
);

function toggleOption(g, label) {
	if (g.selection_type === "Single") {
		modSel[g.group_name] = modSel[g.group_name] === label ? "" : label;
	} else {
		const cur = Array.isArray(modSel[g.group_name]) ? [...modSel[g.group_name]] : [];
		const i = cur.indexOf(label);
		if (i >= 0) cur.splice(i, 1);
		else cur.push(label);
		modSel[g.group_name] = cur;
	}
}

function isPicked(g, label) {
	return pickedLabels(g).includes(label);
}

function initSelection(groups) {
	for (const k of Object.keys(modSel)) delete modSel[k];
	// Pre-select single-group defaults for a faster tap-through.
	for (const g of groups) {
		if (g.selection_type === "Single") {
			const def = (g.options || []).find((o) => o.is_default);
			modSel[g.group_name] = def ? def.label : "";
		} else {
			modSel[g.group_name] = [];
		}
	}
}

function applyGroups(groups) {
	modGroups.value = Array.isArray(groups) ? groups : [];
	initSelection(modGroups.value);
}

async function fetchGroups() {
	if (!props.itemCode) return [];
	try {
		const g = await call("pos_next.api.restaurant.get_item_modifiers", {
			item_code: props.itemCode,
		});
		return Array.isArray(g) ? g : [];
	} catch (e) {
		return [];
	}
}

// Resolve + initialise whenever the dialog opens. The prop path is synchronous so
// the picker is valid/invalid correctly on first render; the fetch path is only
// taken when no groups were supplied.
watch(
	() => props.modelValue,
	(open) => {
		if (!open) return;
		if (Array.isArray(props.groups)) {
			applyGroups(props.groups);
		} else {
			fetchGroups().then(applyGroups);
		}
	},
	{ immediate: true }
);

function confirmModifiers() {
	if (!modValid.value) return;
	const sel = {};
	for (const g of modGroups.value) {
		const picked = pickedLabels(g);
		if (picked.length) sel[g.group_name] = g.selection_type === "Single" ? picked[0] : picked;
	}
	emit("confirm", sel);
	emit("update:modelValue", false);
}
</script>
