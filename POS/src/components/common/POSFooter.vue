<template>
	<!--
		Enfono / Numo: the product footer. POS Next is AGPL-3.0, so the footer keeps the credit and a
		link to this build's source (EnfonoTech/POSNext, public) instead of BrainWise's integrity-checked
		"Powered by" bar; the licence and copyright notices in the source are unchanged.
	-->
	<footer class="numo-pos-footer" dir="ltr">
		<span class="numo-pos-footer-brand">{{ __(BRAND.name) }}</span>
		<span aria-hidden="true">·</span>
		<span>{{ __("Built on POS Next (AGPL-3.0)") }}</span>
		<span aria-hidden="true">·</span>
		<a :href="BRAND.sourceUrl" target="_blank" rel="noopener noreferrer">{{ __("Source code") }}</a>
	</footer>
</template>

<script setup>
import { BRAND } from "@/brand";
</script>

<style scoped>
.numo-pos-footer {
	position: fixed;
	bottom: 0;
	left: 0;
	right: 0;
	z-index: 100;
	display: flex;
	justify-content: center;
	align-items: center;
	gap: 6px;
	padding: 3px 16px;
	font-size: 11.5px;
	color: var(--pos-ink-muted);
	background: var(--pos-panel);
	border-top: 1px solid var(--pos-line);
}

.numo-pos-footer-brand {
	font-weight: 600;
	color: var(--pos-action);
}

.numo-pos-footer a {
	color: var(--pos-action);
	text-decoration: none;
	font-weight: 500;
}

.numo-pos-footer a:hover {
	text-decoration: underline;
}
</style>
