/**
 * Product brand for the Enfono build of POSNext (Numo).
 *
 * Everything the cashier sees as the product's own name or logo comes from here,
 * so a later brand change (or a per-site switch) touches one file. Upstream
 * strings that named the product now take the name as a {0} placeholder, which
 * keeps one translation per sentence instead of one per brand.
 */

const base = import.meta.env.BASE_URL || "/assets/pos_next/pos/"

export const BRAND = Object.freeze({
	/** Product name; passed through __() so Arabic shows نمو. */
	name: "Numo POS",
	/** Square mark for the header button and small spaces. */
	mark: `${base}numo-mark.webp`,
	/** Full bilingual logo with tagline, for the sign-in screen. */
	logo: `${base}numo-logo.webp`,
	/** This build's source (AGPL-3.0: users of the POS can get it). */
	sourceUrl: "https://github.com/EnfonoTech/POSNext",
	/** Browser chrome colour (Numo deep teal). */
	themeColor: "#00403c",
})
