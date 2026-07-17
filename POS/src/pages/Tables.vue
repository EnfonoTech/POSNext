<template>
	<div class="min-h-screen bg-gray-50 flex flex-col">
		<!-- Header -->
		<header class="bg-white shadow">
			<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
				<div class="flex justify-between h-14 items-center">
					<div class="flex items-center space-x-3">
						<h1 class="text-lg font-semibold text-gray-900">{{ __("Tables") }}</h1>
						<span v-if="shiftStore.profileName" class="text-xs text-gray-500">
							{{ shiftStore.profileName }}
						</span>
					</div>
					<nav class="flex items-center space-x-2">
						<router-link to="/sell" class="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-100">
							{{ __("Sell") }}
						</router-link>
						<router-link
							to="/tables"
							class="px-3 py-1.5 text-sm rounded-md bg-blue-50 text-blue-700 font-medium"
						>
							{{ __("Tables") }}
						</router-link>
						<router-link to="/kitchen" class="px-3 py-1.5 text-sm rounded-md text-gray-600 hover:bg-gray-100">
							{{ __("Kitchen") }}
						</router-link>
					</nav>
				</div>
			</div>
		</header>

		<div class="flex-1 max-w-7xl w-full mx-auto px-4 py-4">
			<!-- Floor map picker: tapping a table opens that table's order in the main
			     sell screen (/sell?table=<name>). The live order IS the main cart /
			     per-device draft; occupancy comes from each table's presence session. -->
			<div v-if="loadingTables" class="text-sm text-gray-500 py-8 text-center">
				{{ __("Loading tables...") }}
			</div>
			<div v-else-if="!tables.length" class="text-sm text-gray-500 py-8 text-center">
				{{ __("No tables configured. Create POS Table records in the desk.") }}
			</div>
			<div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
				<button
					v-for="t in tables"
					:key="t.name"
					class="rounded-xl border p-4 text-left transition shadow-sm"
					:class="
						t.occupied
							? 'bg-amber-50 border-amber-300 hover:border-amber-400'
							: 'bg-white border-gray-200 hover:border-blue-400'
					"
					@click="openTable(t)"
				>
					<div class="flex items-center justify-between">
						<span class="font-semibold text-gray-900">{{ t.table_name }}</span>
						<span
							class="h-2.5 w-2.5 rounded-full"
							:class="t.occupied ? 'bg-amber-500' : 'bg-green-500'"
						></span>
					</div>
					<div class="text-xs text-gray-500 mt-1">
						{{ t.area || __("Floor") }} · {{ t.seats || 0 }} {{ __("seats") }}
					</div>
					<div v-if="t.session" class="mt-2 text-sm font-medium text-amber-700">
						{{ formatCurrency(t.session.grand_total) }}
					</div>
				</button>
			</div>

			<div v-if="message" class="mt-3 text-xs" :class="messageIsError ? 'text-red-600' : 'text-green-700'">
				{{ message }}
			</div>
		</div>
	</div>
</template>

<script setup>
import { call } from "@/utils/apiWrapper";
import { usePOSShiftStore } from "@/stores/posShift";
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

const shiftStore = usePOSShiftStore();
const router = useRouter();

const tables = ref([]);
const loadingTables = ref(true);
const message = ref("");
const messageIsError = ref(false);

function formatCurrency(v) {
	const cur = shiftStore.profileCurrency || "SAR";
	return `${(v || 0).toFixed(2)} ${cur}`;
}

function note(msg, isError = false) {
	message.value = msg;
	messageIsError.value = isError;
	setTimeout(() => {
		if (message.value === msg) message.value = "";
	}, 4000);
}

async function loadTables() {
	try {
		tables.value = await call("pos_next.api.restaurant.get_tables", {
			pos_profile: shiftStore.profileName || null,
		});
	} catch (e) {
		note(e?.messages?.[0] || __("Failed to load tables"), true);
	} finally {
		loadingTables.value = false;
	}
}

// Picker: hand the table off to the main sell screen. POSSale reads ?table= on
// mount / route-change and binds the cart (loads that table's draft + touches its
// presence session). The floor-map is now purely a navigation surface — the
// add-item / session panel lives in the main cart.
function openTable(t) {
	router.push("/sell?table=" + encodeURIComponent(t.name));
}

// Realtime refresh + polling fallback so occupancy stays current while browsing.
let pollTimer = null;
function handleTableUpdate() {
	loadTables();
}

onMounted(async () => {
	await shiftStore.checkShift?.();
	loadTables();
	if (window.frappe?.realtime) {
		window.frappe.realtime.on("posnext_table_update", handleTableUpdate);
	}
	pollTimer = setInterval(loadTables, 15000);
});

onUnmounted(() => {
	if (window.frappe?.realtime) {
		window.frappe.realtime.off("posnext_table_update", handleTableUpdate);
	}
	clearInterval(pollTimer);
});
</script>
