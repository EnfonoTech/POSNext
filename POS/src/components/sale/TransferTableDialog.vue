<template>
	<Dialog
		:modelValue="modelValue"
		:options="{ title: __('Transfer to table'), size: 'sm' }"
		@update:modelValue="$emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-3">
				<p class="text-xs text-gray-500">
					{{ __("Move this table's order to a free table. Occupied tables are hidden.") }}
				</p>
				<div v-if="loading" class="py-6 text-center text-sm text-gray-400">
					{{ __("Loading tables…") }}
				</div>
				<div v-else-if="!freeTables.length" class="py-6 text-center text-sm text-gray-400">
					{{ __("No free tables available") }}
				</div>
				<div v-else class="grid grid-cols-3 gap-2">
					<button
						v-for="t in freeTables"
						:key="t.name"
						class="flex flex-col items-center justify-center rounded-lg border px-2 py-3 text-sm transition"
						:class="
							selected === t.name
								? 'border-blue-500 bg-blue-50 text-blue-700'
								: 'border-gray-200 hover:border-blue-300 text-gray-700'
						"
						@click="selected = t.name"
					>
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
				{{ __("Transfer here") }}
			</button>
		</template>
	</Dialog>
</template>

<script setup>
// Free-table picker for a table transfer (Feature 2). Copies the ModifierDialog
// dialog shell. On open it loads the floor via get_tables and shows only free tables
// (no Open session) other than the current one; emits `confirm` with the chosen
// table name (POS Table.name).
import { Dialog } from "frappe-ui";
import { call } from "@/utils/apiWrapper";
import { computed, ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	currentTable: { type: String, default: null },
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

const freeTables = computed(() =>
	tables.value.filter((t) => !t.occupied && t.name !== props.currentTable)
);

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
