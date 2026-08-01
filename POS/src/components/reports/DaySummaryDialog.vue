<template>
	<div
		v-if="modelValue"
		class="fixed inset-0 z-[300] flex items-center justify-center bg-black/40 p-4"
		@click.self="close"
	>
		<div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
			<!-- Header -->
			<div class="flex items-center gap-3 px-5 py-4 border-b border-gray-100">
				<div
					class="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center flex-shrink-0"
				>
					<svg
						class="w-5 h-5 text-emerald-600"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
						/>
					</svg>
				</div>
				<div class="flex-1 min-w-0">
					<h2 class="text-base font-semibold text-gray-900">{{ __("Day Summary") }}</h2>
					<p class="text-xs text-gray-500 truncate">
						{{ summary?.pos_profile || posProfile || "" }}
						<span v-if="summary?.branch"> · {{ summary.branch }}</span>
					</p>
				</div>
				<button
					@click="close"
					class="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400"
					:aria-label="__('Close')"
				>
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M6 18L18 6M6 6l12 12"
						/>
					</svg>
				</button>
			</div>

			<!-- Controls -->
			<div class="px-5 py-3 border-b border-gray-100 flex flex-wrap items-end gap-3">
				<label class="flex flex-col gap-1">
					<span class="text-xs text-gray-500">{{ __("Date") }}</span>
					<input
						v-model="date"
						type="date"
						class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
						@change="load"
					/>
				</label>
				<label v-if="(summary?.profiles || []).length > 1" class="flex flex-col gap-1">
					<span class="text-xs text-gray-500">{{ __("Till") }}</span>
					<select
						v-model="profile"
						class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
						@change="load"
					>
						<option v-for="p in summary.profiles" :key="p" :value="p">{{ p }}</option>
					</select>
				</label>
				<button
					@click="load"
					class="ms-auto px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700"
				>
					{{ __("Refresh") }}
				</button>
			</div>

			<!-- Body -->
			<div class="flex-1 overflow-y-auto px-5 py-4">
				<div v-if="loading" class="py-12 text-center text-sm text-gray-500">
					{{ __("Loading") }}…
				</div>

				<div
					v-else-if="error"
					class="py-8 px-4 text-center text-sm text-red-600 bg-red-50 rounded-xl"
				>
					{{ error }}
				</div>

				<table v-else-if="rows.length" class="w-full text-sm">
					<thead>
						<tr class="text-xs uppercase text-gray-500 border-b border-gray-200">
							<th class="text-start py-2 font-medium">{{ __("Particulars") }}</th>
							<th class="text-end py-2 font-medium">{{ __("Income") }}</th>
							<th class="text-end py-2 font-medium">{{ __("Expense") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="(r, i) in rows"
							:key="i"
							class="border-b border-gray-50"
							:class="isTotalRow(r) ? 'font-semibold text-gray-900' : 'text-gray-700'"
						>
							<td class="py-2" :style="{ paddingInlineStart: (r.indent || 0) * 16 + 'px' }">
								{{ r.particulars }}
								<span
									v-if="r.invoices"
									class="ms-2 text-xs text-gray-400"
								>
									{{ r.invoices }} {{ __("bills") }}
								</span>
								<span
									v-if="r.variance !== null && r.variance !== undefined"
									class="ms-2 text-xs"
									:class="r.variance == 0 ? 'text-emerald-600' : 'text-red-600'"
								>
									{{ r.variance == 0 ? __("balanced") : money(r.variance) }}
								</span>
							</td>
							<td class="py-2 text-end tabular-nums">
								{{ r.income === null || r.income === undefined ? "" : money(r.income) }}
							</td>
							<td class="py-2 text-end tabular-nums text-red-600">
								{{ r.expense === null || r.expense === undefined ? "" : money(r.expense) }}
							</td>
						</tr>
					</tbody>
				</table>

				<div v-else class="py-12 text-center text-sm text-gray-500">
					{{ __("No sales for this day yet") }}
				</div>
			</div>

			<div class="px-5 py-3 border-t border-gray-100 flex justify-end">
				<button
					@click="close"
					class="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800"
				>
					{{ __("Close") }}
				</button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, watch } from "vue";
import { call } from "frappe-ui";
import { formatCurrency } from "@/utils/currency";
import { logger } from "@/utils/logger";

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	posProfile: { type: String, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const loading = ref(false);
const error = ref(null);
const summary = ref(null);
const rows = ref([]);
const profile = ref(null);
const date = ref(today());

function today() {
	const d = new Date();
	const p = (n) => String(n).padStart(2, "0");
	return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

function money(v) {
	return formatCurrency(v || 0, summary.value?.currency || "SAR");
}

// rows the DCR emits at indent 0 that read as subtotals
function isTotalRow(r) {
	return !r.indent;
}

async function load() {
	loading.value = true;
	error.value = null;
	try {
		const res = await call("pos_next.api.dcr.get_day_summary", {
			pos_profile: profile.value || props.posProfile || undefined,
			from_date: date.value,
			to_date: date.value,
		});
		summary.value = res;
		rows.value = res.rows || [];
		profile.value = res.pos_profile;
	} catch (e) {
		// the endpoint refuses tills the user is not scoped to — surface it plainly
		error.value = e?.message || e?.exc_type || String(e);
		rows.value = [];
		logger.error("Day summary failed", e);
	} finally {
		loading.value = false;
	}
}

function close() {
	emit("update:modelValue", false);
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) {
			date.value = today();
			profile.value = props.posProfile || null;
			load();
		}
	}
);
</script>
