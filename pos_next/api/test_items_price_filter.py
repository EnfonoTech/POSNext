# Copyright (c) 2026, Enfono Technologies and contributors
# See license.txt

"""The price list drives the menu.

An item appears on a till only once somebody has priced it there. These tests pin the
rules that decide "priced", because every one of them is a way for an item to appear or
vanish from a cashier's screen without anybody editing the item.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from pos_next.api.items import (
	_build_item_base_conditions,
	_only_priced_items,
	_priced_item_condition,
)


def _profile(**over):
	d = frappe._dict(
		name="Test POS", selling_price_list="Branch List", custom_only_priced_items=1,
		item_groups=[], warehouse="Stores - T",
	)
	d.update(over)
	return d


class TestTheSwitchIsOffByDefault(FrappeTestCase):
	"""POSNext runs for clients whose catalogues predate any price list. Shortening
	their menus unasked would be an outage of our making."""

	def test_a_profile_without_the_field_is_unfiltered(self):
		self.assertFalse(_only_priced_items(frappe._dict(selling_price_list="X")))

	def test_an_unticked_profile_is_unfiltered(self):
		self.assertFalse(_only_priced_items(_profile(custom_only_priced_items=0)))

	def test_no_condition_is_produced_when_off(self):
		sql, params = _priced_item_condition(_profile(custom_only_priced_items=0))
		self.assertIsNone(sql)
		self.assertEqual(params, [])

	def test_the_base_query_is_untouched_when_off(self):
		conditions, _params, _joins = _build_item_base_conditions(
			_profile(custom_only_priced_items=0))
		self.assertFalse(any("tabItem Price" in c for c in conditions))

	def test_a_profile_with_no_price_list_cannot_filter(self):
		"""Filtering on an empty price list would hide the entire menu."""
		sql, _ = _priced_item_condition(_profile(selling_price_list=None))
		self.assertIsNone(sql)


class TestWhatCountsAsPriced(FrappeTestCase):
	def setUp(self):
		self.sql, self.params = _priced_item_condition(_profile())

	def test_it_filters_on_the_profiles_own_price_list(self):
		self.assertEqual(self.params[0], "Branch List")

	def test_both_date_bounds_are_checked_against_today(self):
		self.assertEqual(self.params[1], nowdate())
		self.assertEqual(self.params[2], nowdate())
		self.assertIn("ip.valid_from IS NULL OR ip.valid_from <= %s", self.sql)
		self.assertIn("ip.valid_upto IS NULL OR ip.valid_upto >= %s", self.sql)

	def test_a_zero_rate_is_not_a_price(self):
		"""A zero-priced button rings up free — worse than the item being absent."""
		self.assertIn("IFNULL(ip.price_list_rate, 0) > 0", self.sql)

	def test_buying_rows_do_not_put_an_item_on_the_menu(self):
		self.assertIn("ip.selling = 1", self.sql)

	def test_a_party_specific_price_does_not_expose_an_item_to_everyone(self):
		self.assertIn("IFNULL(ip.customer, '') = ''", self.sql)
		self.assertIn("IFNULL(ip.supplier, '') = ''", self.sql)

	def test_a_template_is_priced_when_any_of_its_variants_is(self):
		"""get_items already renders such a template at its cheapest variant's price;
		hiding it here would contradict that."""
		self.assertIn("v.variant_of = i.name", self.sql)
		self.assertIn("v.disabled = 0", self.sql)


class TestItReachesEveryItemQuery(FrappeTestCase):
	"""get_items, get_items_bulk and get_items_count all route through the one builder,
	so the grid, its pagination and its count cannot disagree about what exists."""

	def test_the_condition_is_appended_when_on(self):
		conditions, params, _joins = _build_item_base_conditions(_profile())
		self.assertTrue(any("tabItem Price" in c for c in conditions))
		self.assertIn("Branch List", params)

	def test_every_caller_shares_the_builder(self):
		import inspect
		from pos_next.api import items
		for fn in (items.get_items, items.get_items_bulk, items.get_items_count):
			self.assertIn("_build_item_base_conditions", inspect.getsource(fn),
			              f"{fn.__name__} must not build its own conditions")

	def test_join_params_still_precede_where_params(self):
		"""The builder returns raw SQL with %s in order; a swap here silently mismatches
		the warehouse filter against the price list."""
		_c, params, joins = _build_item_base_conditions(
			_profile(), hide_unavailable=True, warehouse="Stores - T")
		self.assertIn("tabBin", joins)
		self.assertEqual(params[0], "Stores - T", "warehouse join param must come first")
		self.assertIn("Branch List", params[1:])


class TestTheGroupTabsFollowTheSameRule(FrappeTestCase):
	def test_tabs_are_narrowed_to_groups_holding_something_sellable(self):
		import inspect
		from pos_next.api import items
		src = inspect.getsource(items.get_item_groups)
		self.assertIn("_groups_with_priced_items", src)

	def test_an_unfiltered_profile_keeps_every_group(self):
		from pos_next.api.items import _groups_with_priced_items
		groups = ["Breakfast", "Lunch Special"]
		self.assertEqual(
			_groups_with_priced_items(_profile(custom_only_priced_items=0), groups), groups)

	def test_no_groups_in_means_no_query_out(self):
		from pos_next.api.items import _groups_with_priced_items
		self.assertEqual(_groups_with_priced_items(_profile(), []), [])


class TestAddingAPriceShowsUpAtOnce(FrappeTestCase):
	"""A manager prices an item, sees no new tab, and reports the feature broken."""

	def test_the_item_price_hook_is_registered_for_all_three_events(self):
		from pos_next import hooks
		ev = hooks.doc_events.get("Item Price") or {}
		for e in ("after_insert", "on_update", "on_trash"):
			self.assertEqual(ev.get(e), "pos_next.api.items.on_item_price_change",
			                 f"Item Price {e} must bust the cached tabs")

	def test_the_hook_clears_the_group_cache_for_every_profile(self):
		from unittest.mock import patch
		from pos_next.api import items
		cleared = []

		class _Cache:
			def delete_value(self, key):
				cleared.append(key)

		with patch.object(items.frappe, "get_all", return_value=["A POS", "B POS"]), \
		     patch.object(items.frappe, "cache", return_value=_Cache()):
			items.on_item_price_change(frappe._dict())
		self.assertEqual(cleared, ["pos_item_groups:A POS", "pos_item_groups:B POS"])


class TestTheSwitchIsInstalled(FrappeTestCase):
	def test_the_field_is_created_on_install_and_on_migrate(self):
		import inspect
		from pos_next import install
		self.assertIn("ensure_custom_fields", inspect.getsource(install.after_install))
		self.assertIn("ensure_custom_fields", inspect.getsource(install.after_migrate))

	def test_it_defaults_to_off(self):
		import inspect
		from pos_next import install
		src = inspect.getsource(install.ensure_custom_fields)
		self.assertIn('"default": "0"', src)
		self.assertIn("custom_only_priced_items", src)
