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

		<div class="flex-1 max-w-7xl w-full mx-auto px-4 py-4 flex gap-4">
			<!-- Floor map -->
			<div class="flex-1">
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
						:class="[
							t.occupied
								? 'bg-amber-50 border-amber-300 hover:border-amber-400'
								: 'bg-white border-gray-200 hover:border-blue-400',
							selectedTable === t.name ? 'ring-2 ring-blue-500' : '',
						]"
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
			</div>

			<!-- Session panel -->
			<div v-if="session" class="w-96 shrink-0 bg-white rounded-xl shadow border border-gray-200 flex flex-col">
				<div class="p-3 border-b flex items-center justify-between">
					<div>
						<div class="font-semibold text-gray-900">{{ session.table_label }}</div>
						<div class="text-xs text-gray-500">{{ session.name }}</div>
					</div>
					<button class="text-gray-400 hover:text-gray-600 text-xl leading-none" @click="closePanel">
						×
					</button>
				</div>

				<!-- Add item -->
				<div class="p-3 border-b space-y-2">
					<div class="relative">
						<input
							v-model="itemQuery"
							type="text"
							:placeholder="__('Search item...')"
							class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
							@input="searchItems"
						/>
						<div
							v-if="itemResults.length"
							class="absolute z-10 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow max-h-48 overflow-auto"
						>
							<button
								v-for="r in itemResults"
								:key="r.value"
								class="block w-full text-left px-3 py-2 text-sm hover:bg-blue-50"
								@click="pickItem(r.value)"
							>
								<span class="font-medium">{{ r.value }}</span>
								<span v-if="r.description" class="text-gray-500"> — {{ r.description }}</span>
							</button>
						</div>
					</div>
				</div>

				<!-- Lines -->
				<div class="flex-1 overflow-auto p-3 space-y-2">
					<div v-if="!session.items.length" class="text-sm text-gray-400 text-center py-6">
						{{ __("No items yet") }}
					</div>
					<div
						v-for="line in session.items"
						:key="line.row"
						class="flex items-center justify-between rounded-lg border px-3 py-2"
						:class="line.sent_to_kitchen ? 'bg-gray-50 border-gray-200' : 'bg-white border-blue-200'"
					>
						<div class="min-w-0">
							<div class="text-sm font-medium text-gray-900 truncate">{{ line.item_name }}</div>
							<div class="text-xs text-gray-500">
								{{ formatCurrency(line.rate) }} × {{ line.qty }} = {{ formatCurrency(line.amount) }}
								<span v-if="line.sent_to_kitchen" class="ml-1 text-amber-600">🔥 {{ __("Sent") }}</span>
							</div>
						</div>
						<div v-if="!line.sent_to_kitchen" class="flex items-center space-x-1 ml-2">
							<button class="h-6 w-6 rounded bg-gray-100 hover:bg-gray-200 text-sm" @click="setQty(line, line.qty - 1)">
								−
							</button>
							<span class="text-sm w-6 text-center">{{ line.qty }}</span>
							<button class="h-6 w-6 rounded bg-gray-100 hover:bg-gray-200 text-sm" @click="setQty(line, line.qty + 1)">
								+
							</button>
						</div>
					</div>
				</div>

				<!-- Actions -->
				<div class="p-3 border-t space-y-2">
					<div class="flex justify-between text-sm font-semibold text-gray-900">
						<span>{{ __("Total") }}</span>
						<span>{{ formatCurrency(session.grand_total) }}</span>
					</div>
					<div class="grid grid-cols-2 gap-2">
						<button
							class="rounded-md bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium py-2 disabled:opacity-50"
							:disabled="busy || !hasUnsent"
							@click="sendKitchen"
						>
							{{ __("Send to Kitchen") }}
						</button>
						<button
							class="rounded-md bg-green-600 hover:bg-green-700 text-white text-sm font-medium py-2 disabled:opacity-50"
							:disabled="busy || !session.items.length"
							@click="settle"
						>
							{{ __("Settle (Cash)") }}
						</button>
					</div>
					<button
						class="w-full rounded-md border border-red-200 text-red-600 hover:bg-red-50 text-sm py-1.5 disabled:opacity-50"
						:disabled="busy"
						@click="cancelSession"
					>
						{{ __("Cancel Session") }}
					</button>
					<div v-if="message" class="text-xs" :class="messageIsError ? 'text-red-600' : 'text-green-700'">
						{{ message }}
					</div>
				</div>
			</div>
		</div>

		<!-- Modifier picker -->
		<Dialog v-model="modOpen" :options="{ title: __('Choose options'), size: 'sm' }">
			<template #body-content>
				<div v-if="modItem" class="space-y-4">
					<div class="text-sm font-medium text-gray-900">{{ modItem.code }}</div>
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
						<span class="font-medium">+{{ modDeltaTotal.toFixed(2) }} {{ shiftStore.profileCurrency || "SAR" }}</span>
					</div>
				</div>
			</template>
			<template #actions>
				<button
					class="w-full rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 disabled:opacity-50"
					:disabled="!modValid || busy"
					@click="confirmModifiers"
				>
					{{ __("Add to order") }}
				</button>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { Dialog } from "frappe-ui";
import { call } from "@/utils/apiWrapper";
import { usePOSShiftStore } from "@/stores/posShift";
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";

const shiftStore = usePOSShiftStore();

const tables = ref([]);
const loadingTables = ref(true);
const selectedTable = ref(null);
const session = ref(null);
const itemQuery = ref("");
const itemResults = ref([]);
const busy = ref(false);
const message = ref("");
const messageIsError = ref(false);

// Modifier picker dialog state
const modOpen = ref(false);
const modItem = ref(null); // { code }
const modGroups = ref([]); // resolved groups from get_item_modifiers
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

const hasUnsent = computed(() => (session.value?.items || []).some((l) => !l.sent_to_kitchen && l.qty > 0));

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

async function openTable(t) {
	selectedTable.value = t.name;
	busy.value = true;
	try {
		session.value = await call("pos_next.api.restaurant.get_session", {
			table: t.name,
			create: 1,
			pos_profile: shiftStore.profileName || null,
		});
	} catch (e) {
		note(e?.messages?.[0] || __("Failed to open table"), true);
	} finally {
		busy.value = false;
	}
	loadTables();
}

function closePanel() {
	session.value = null;
	selectedTable.value = null;
}

let searchTimer = null;
function searchItems() {
	clearTimeout(searchTimer);
	if (!itemQuery.value || itemQuery.value.length < 2) {
		itemResults.value = [];
		return;
	}
	searchTimer = setTimeout(async () => {
		try {
			const res = await call("frappe.desk.search.search_link", {
				doctype: "Item",
				txt: itemQuery.value,
				filters: { disabled: 0 },
			});
			itemResults.value = res || [];
		} catch (e) {
			itemResults.value = [];
		}
	}, 250);
}

async function pickItem(itemCode) {
	itemQuery.value = "";
	itemResults.value = [];
	// Ask the server which modifier groups this item offers. If none, add it
	// straight away; otherwise open the picker so the cashier chooses options.
	let groups = [];
	try {
		groups = await call("pos_next.api.restaurant.get_item_modifiers", { item_code: itemCode });
	} catch (e) {
		groups = [];
	}
	if (Array.isArray(groups) && groups.length) {
		modItem.value = { code: itemCode };
		modGroups.value = groups;
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
		modOpen.value = true;
	} else {
		await addItem(itemCode, null);
	}
}

async function confirmModifiers() {
	if (!modValid.value) return;
	const sel = {};
	for (const g of modGroups.value) {
		const picked = pickedLabels(g);
		if (picked.length) sel[g.group_name] = g.selection_type === "Single" ? picked[0] : picked;
	}
	const code = modItem.value.code;
	modOpen.value = false;
	await addItem(code, sel);
}

async function addItem(itemCode, modifiers) {
	busy.value = true;
	try {
		const params = {
			session: session.value.name,
			item_code: itemCode,
			qty: 1,
		};
		if (modifiers && Object.keys(modifiers).length) {
			params.modifiers = JSON.stringify(modifiers);
		}
		session.value = await call("pos_next.api.restaurant.session_add_item", params);
	} catch (e) {
		note(e?.messages?.[0] || __("Failed to add item"), true);
	} finally {
		busy.value = false;
	}
}

async function setQty(line, qty) {
	busy.value = true;
	try {
		session.value = await call("pos_next.api.restaurant.session_set_qty", {
			session: session.value.name,
			row: line.row,
			qty,
		});
	} catch (e) {
		note(e?.messages?.[0] || __("Failed to update qty"), true);
	} finally {
		busy.value = false;
	}
}

async function sendKitchen() {
	busy.value = true;
	try {
		const res = await call("pos_next.api.restaurant.session_send_kitchen", {
			session: session.value.name,
		});
		session.value = res.session;
		if (res.kot) note(__("Sent to kitchen") + ": " + res.kot);
	} catch (e) {
		note(e?.messages?.[0] || __("Failed to send to kitchen"), true);
	} finally {
		busy.value = false;
	}
}

async function settle() {
	busy.value = true;
	try {
		// Build one consolidated POS invoice through the standard POSNext path
		const items = session.value.items
			.filter((l) => l.qty > 0)
			.map((l) => ({ item_code: l.item_code, qty: l.qty, rate: l.rate }));
		const total = session.value.grand_total;
		const draft = await call("pos_next.api.invoices.update_invoice", {
			data: {
				doctype: "Sales Invoice",
				is_pos: 1,
				pos_profile: shiftStore.profileName,
				company: shiftStore.profileCompany,
				customer: session.value.customer || shiftStore.profileCustomer || "Walk-in Customer",
				posa_pos_opening_shift: shiftStore.currentShift?.name,
				items,
				payments: [{ mode_of_payment: "Cash", amount: total }],
			},
		});
		const payments = (draft.payments || []).map((p) =>
			p.mode_of_payment === "Cash" ? { ...p, amount: total } : p
		);
		const submitted = await call("pos_next.api.invoices.submit_invoice", {
			invoice: { ...draft, payments },
			data: {},
		});
		const res = await call("pos_next.api.restaurant.session_settle", {
			session: session.value.name,
			sales_invoice: submitted.name,
		});
		note(__("Settled") + ": " + submitted.name);
		session.value = null;
		selectedTable.value = null;
		loadTables();
	} catch (e) {
		note(e?.messages?.[0] || __("Settle failed"), true);
	} finally {
		busy.value = false;
	}
}

async function cancelSession() {
	busy.value = true;
	try {
		await call("pos_next.api.restaurant.session_cancel", { session: session.value.name });
		session.value = null;
		selectedTable.value = null;
		loadTables();
	} catch (e) {
		note(e?.messages?.[0] || __("Cancel failed"), true);
	} finally {
		busy.value = false;
	}
}

// Realtime refresh + polling fallback
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
