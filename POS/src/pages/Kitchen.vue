<template>
	<div class="min-h-screen bg-gray-900 flex flex-col">
		<!-- Header -->
		<header class="bg-gray-800 shadow">
			<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
				<div class="flex justify-between h-14 items-center">
					<div class="flex items-center space-x-3">
						<h1 class="text-lg font-semibold text-white">{{ __("Kitchen Display") }}</h1>
						<span class="text-xs text-gray-400">{{ tickets.length }} {{ __("open") }}</span>
					</div>
					<nav class="flex items-center space-x-2">
						<router-link to="/" class="px-3 py-1.5 text-sm rounded-md text-gray-300 hover:bg-gray-700">
							{{ __("Sell") }}
						</router-link>
						<router-link to="/tables" class="px-3 py-1.5 text-sm rounded-md text-gray-300 hover:bg-gray-700">
							{{ __("Tables") }}
						</router-link>
						<router-link
							to="/kitchen"
							class="px-3 py-1.5 text-sm rounded-md bg-gray-700 text-white font-medium"
						>
							{{ __("Kitchen") }}
						</router-link>
					</nav>
				</div>
			</div>
		</header>

		<div class="flex-1 max-w-7xl w-full mx-auto px-4 py-4">
			<div v-if="!tickets.length" class="text-gray-500 text-center py-16 text-lg">
				{{ __("No open tickets") }} 🎉
			</div>
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
				<div
					v-for="t in tickets"
					:key="t.name"
					class="bg-gray-800 rounded-xl border border-gray-700 flex flex-col overflow-hidden"
				>
					<div class="px-3 py-2 bg-gray-700 flex items-center justify-between">
						<div>
							<div class="text-white font-semibold">{{ t.table_label || __("Takeaway") }}</div>
							<div class="text-xs text-gray-400">{{ t.name }} · {{ elapsed(t.ordered_at) }}</div>
						</div>
						<button
							class="text-xs bg-green-600 hover:bg-green-700 text-white rounded px-2 py-1"
							@click="completeTicket(t)"
						>
							{{ __("Done") }}
						</button>
					</div>
					<div class="p-2 space-y-1">
						<button
							v-for="i in t.items"
							:key="i.row"
							class="w-full flex items-center justify-between rounded-lg px-3 py-2 text-left"
							:class="
								i.status === 'Ready'
									? 'bg-green-900/40 text-green-300 line-through'
									: 'bg-gray-700/60 text-white hover:bg-gray-600'
							"
							@click="toggleItem(t, i)"
						>
							<span class="text-sm">
								<span class="font-bold mr-2">{{ i.qty }}×</span>{{ i.item_name }}
								<span v-if="i.notes" class="block text-xs text-amber-300">{{ i.notes }}</span>
							</span>
							<span class="text-xs ml-2">{{ i.status === "Ready" ? "✓" : "" }}</span>
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { usePOSShiftStore } from "@/stores/posShift";
import { onMounted, onUnmounted, ref } from "vue";

const shiftStore = usePOSShiftStore();
const tickets = ref([]);
const now = ref(Date.now());

function elapsed(orderedAt) {
	const start = new Date((orderedAt || "").replace(" ", "T")).getTime();
	if (!start || Number.isNaN(start)) return "";
	const mins = Math.max(0, Math.floor((now.value - start) / 60000));
	return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

async function load() {
	try {
		tickets.value = await call("pos_next.api.restaurant.kot_active", {
			pos_profile: shiftStore.profileName || null,
		});
	} catch (e) {
		// keep last state; KDS should not blank out on a transient error
	}
}

async function toggleItem(t, i) {
	try {
		await call("pos_next.api.restaurant.kot_item_ready", {
			kot: t.name,
			row: i.row,
			ready: i.status === "Ready" ? 0 : 1,
		});
	} finally {
		load();
	}
}

async function completeTicket(t) {
	try {
		await call("pos_next.api.restaurant.kot_complete", { kot: t.name });
	} finally {
		load();
	}
}

let pollTimer = null;
let clockTimer = null;
function handleKotUpdate() {
	load();
}

onMounted(async () => {
	await shiftStore.checkShift?.();
	load();
	if (window.frappe?.realtime) {
		window.frappe.realtime.on("posnext_kot_update", handleKotUpdate);
	}
	pollTimer = setInterval(load, 10000);
	clockTimer = setInterval(() => (now.value = Date.now()), 30000);
});

onUnmounted(() => {
	if (window.frappe?.realtime) {
		window.frappe.realtime.off("posnext_kot_update", handleKotUpdate);
	}
	clearInterval(pollTimer);
	clearInterval(clockTimer);
});
</script>
