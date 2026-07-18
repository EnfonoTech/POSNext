<template>
	<Dialog
		:modelValue="modelValue"
		:options="{ title: __('Select table'), size: 'sm' }"
		@update:modelValue="$emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-3">
				<p class="text-xs text-gray-500">
					{{ __("Bind this order to a table. Occupied tables open their running order.") }}
				</p>
				<div v-if="loading" class="py-6 text-center text-sm text-gray-400">
					{{ __("Loading tables…") }}
				</div>
				<div v-else-if="!tables.length" class="py-6 text-center text-sm text-gray-400">
					{{ __("No tables configured. Create POS Table records in the desk.") }}
				</div>
				<div v-else class="grid grid-cols-3 gap-2">
					<button
						v-for="t in tables"
						:key="t.name"
						class="relative flex flex-col items-center justify-center rounded-lg border px-2 py-3 text-sm transition"
						:class="[
							selected === t.name
								? 'border-blue-500 bg-blue-50 text-blue-700'
								: t.occupied
									? 'border-amber-300 bg-amber-50 text-amber-800 hover:border-amber-400'
									: 'border-gray-200 hover:border-blue-300 text-gray-700',
						]"
						@click="selected = t.name"
					>
						<span
							class="absolute top-1.5 right-1.5 h-2 w-2 rounded-full"
							:class="t.occupied ? 'bg-amber-500' : 'bg-green-500'"
						></span>
						<span class="font-semibold truncate max-w-full">{{ t.table_name || t.name }}</span>
						<span v-if="t.area" class="text-[10px] text-gray-400 truncate max-w-full">{{ t.area }}</span>
					</button>
				</div>
			</div>
		</template>
		<template #actions>
			<button
				class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 disabled:opacity-50"
				:disabled="!selected"
				@click="confirm"
			>
				{{ __("Open table") }}
			</button>
		</template>
	</Dialog>
</template>

<script setup>
// Inline table picker for binding the main cart to a table without leaving the
// sell screen (mirrors TransferTableDialog). Shows ALL active tables — free ones
// start a fresh order, occupied ones load that table's running order. Emits
// `confirm` with the chosen POS Table name; POSSale calls restaurantStore.openTable.
import { Dialog } from "frappe-ui";
import { call } from "@/utils/apiWrapper";
import { ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	posProfile: { type: String, default: null },
});
const emit = defineEmits(["confirm", "update:modelValue"]);

const __ = (msg, replace, ctx) =>
	typeof window !== "undefined" && typeof window.__ === "function"
		? window.__(msg, replace, ctx)
		: msg;

const tables = ref([]);
const loading = ref(false);
const selected = ref(null);

async function loadTables() {
	loading.value = true;
	selected.value = null;
	try {
		const rows = await call("pos_next.api.restaurant.get_tables", {
			pos_profile: props.posProfile || null,
		});
		tables.value = Array.isArray(rows) ? rows : [];
	} catch (e) {
		tables.value = [];
	} finally {
		loading.value = false;
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) loadTables();
	}
);

function confirm() {
	if (!selected.value) return;
	emit("confirm", selected.value);
	emit("update:modelValue", false);
}
</script>
