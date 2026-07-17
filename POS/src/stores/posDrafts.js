import {
	deleteDraft,
	getDraftsCount,
	saveDraft,
	getAllDrafts,
	updateDraft,
} from "@/utils/draftManager";
import { useToast } from "@/composables/useToast";
import { defineStore } from "pinia";
import { ref } from "vue";

export const usePOSDraftsStore = defineStore("posDrafts", () => {
	// Use custom toast
	const { showSuccess, showError, showWarning } = useToast();

	// State
	const draftsCount = ref(0);
	const drafts = ref([]);

	// Actions
	async function updateDraftsCount() {
		try {
			draftsCount.value = await getDraftsCount();
		} catch (error) {
			console.error("Error getting drafts count:", error);
		}
	}

	async function loadDrafts() {
		try {
			drafts.value = await getAllDrafts();
			draftsCount.value = drafts.value.length;
		} catch (error) {
			console.error("Error loading drafts:", error);
		}
	}

	async function saveDraftInvoice(
		invoiceItems,
		customer,
		posProfile,
		appliedOffers = [],
		draftId = null,
		table = null
	) {
		if (invoiceItems.length === 0) {
			showWarning(__("Cannot save an empty cart as draft"));
			return null;
		}

		try {
			const draftData = {
				pos_profile: posProfile,
				customer: customer,
				items: invoiceItems,
				applied_offers: appliedOffers, // Save applied offers
			};

			// Restaurant dine-in (Q4 LOCKED: no DB migration): tag the draft with its
			// table so the floor picker can re-open the exact in-progress order. The
			// field rides the existing draftData spread into IndexedDB and is filtered
			// in memory by findDraftByTable. Only set for table-bound (dine-in) drafts
			// so retail holds are unchanged.
			if (table) {
				draftData.table = table;
			}

			let savedDraft;
			if (draftId) {
				savedDraft = await updateDraft(draftId, draftData);
			} else {
				savedDraft = await saveDraft(draftData);
			}

			await loadDrafts(); // Refresh drafts list and count

			showSuccess(__("Invoice saved as draft successfully"));

			return savedDraft;
		} catch (error) {
			console.error("Error saving draft:", error);
			showError(__("Failed to save draft"));
			return null;
		}
	}

	async function loadDraft(draft) {
		try {
			showSuccess(__("Draft invoice loaded successfully"));

			return {
				items: draft.items || [],
				customer: draft.customer,
				applied_offers: draft.applied_offers || [], // Restore applied offers
				table: draft.table || null, // Restore restaurant table binding (Q4)
			};
		} catch (error) {
			console.error("Error loading draft:", error);
			showError(__("Failed to load draft"));
			throw error;
		}
	}

	/**
	 * Find the newest draft bound to a given restaurant table (Q4: no DB index —
	 * drafts are filtered in memory). Returns null when the table has no draft.
	 * getAllDrafts is newest-first, so the first match is the current order.
	 */
	async function findDraftByTable(table) {
		if (!table) return null;
		try {
			const all = await getAllDrafts();
			return all.find((d) => d.table === table) || null;
		} catch (error) {
			console.error("Error finding draft by table:", error);
			return null;
		}
	}

	async function deleteDraftById(draftId) {
		try {
			await deleteDraft(draftId);
			await loadDrafts(); // Refresh drafts list and count
			showSuccess(__("Draft deleted successfully"));
		} catch (error) {
			console.error("Error deleting draft:", error);
			showError(__("Failed to delete draft"));
		}
	}

	return {
		// State
		draftsCount,
		drafts,

		// Actions
		updateDraftsCount,
		loadDrafts,
		saveDraftInvoice,
		loadDraft,
		findDraftByTable,
		deleteDraft: deleteDraftById,
	};
});
