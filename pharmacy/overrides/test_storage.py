# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from pharmacy.overrides.storage import validate_bin_capacity, validate_storage
from pharmacy.tests.utils import make_test_item

AMBIENT_ITEM = "_Test Storage Ambient Item"
BELOW_25C_ITEM = "_Test Storage Below 25C Item"
COLD_ITEM = "_Test Storage 2-8C Item"
NO_COND_ITEM = "_Test Storage No Cond Item"
SCHED_X_ITEM = "_Test Storage Schedule X Item"
NDPS_ITEM = "_Test Storage NDPS Item"


def make_warehouse(name, parent, is_group=0, **kwargs):
	company = frappe.db.get_value("Company", {})
	abbr = frappe.db.get_value("Company", company, "abbr")
	full_name = f"{name} - {abbr}"
	if not frappe.db.exists("Warehouse", full_name):
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": name,
				"company": company,
				"parent_warehouse": parent,
				"is_group": is_group,
				**kwargs,
			}
		).insert()
		return doc.name
	# update kwargs if exists
	if kwargs:
		frappe.db.set_value("Warehouse", full_name, kwargs)
	return full_name


class TestStorageRules(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_test_item(AMBIENT_ITEM, nir_storage_condition="Ambient", nir_regulatory_category="OTC")
		make_test_item(BELOW_25C_ITEM, nir_storage_condition="Below 25C", nir_regulatory_category="OTC")
		make_test_item(COLD_ITEM, nir_storage_condition="2-8C", nir_regulatory_category="OTC")
		make_test_item(NO_COND_ITEM, nir_storage_condition="Ambient", nir_regulatory_category="OTC")
		frappe.db.set_value("Item", NO_COND_ITEM, "nir_storage_condition", None)
		make_test_item(SCHED_X_ITEM, nir_storage_condition="Ambient", nir_regulatory_category="Schedule X")
		make_test_item(NDPS_ITEM, nir_storage_condition="Ambient", nir_regulatory_category="NDPS")

		root = frappe.db.get_value("Warehouse", {"is_group": 1, "parent_warehouse": ("is", "not set")})
		dc = make_warehouse("_Test Storage DC", root, is_group=1, nir_warehouse_role="DC")

		# Cold zone (2-8C) and bin
		cold_zone = make_warehouse("_Test Storage Cold Zone", dc, is_group=1, nir_warehouse_role="Zone", nir_storage_condition="2-8C")
		cls.cold_bin = make_warehouse("_Test Storage Cold Bin", cold_zone, nir_warehouse_role="Bin")

		# Cool zone (Below 25C) and bin
		cool_zone = make_warehouse("_Test Storage Cool Zone", dc, is_group=1, nir_warehouse_role="Zone", nir_storage_condition="Below 25C")
		cls.cool_bin = make_warehouse("_Test Storage Cool Bin", cool_zone, nir_warehouse_role="Bin")

		# Ambient zone and bin
		ambient_zone = make_warehouse("_Test Storage Ambient Zone", dc, is_group=1, nir_warehouse_role="Zone", nir_storage_condition="Ambient")
		cls.ambient_bin = make_warehouse("_Test Storage Ambient Bin", ambient_zone, nir_warehouse_role="Bin")

		# Unspecified condition zone and bin (must be treated as Ambient)
		unspec_zone = make_warehouse("_Test Storage Unspec Zone", dc, is_group=1, nir_warehouse_role="Zone", nir_storage_condition=None)
		cls.unspec_bin = make_warehouse("_Test Storage Unspec Bin", unspec_zone, nir_warehouse_role="Bin", nir_storage_condition=None)

		# Scheduled drug cage zone and bin
		cage_zone = make_warehouse("_Test Storage Cage Zone", dc, is_group=1, nir_warehouse_role="Zone", nir_zone_type="Scheduled Drug Cage")
		cls.cage_bin = make_warehouse("_Test Storage Cage Bin", cage_zone, nir_warehouse_role="Bin")

		# General zone and bin
		gen_zone = make_warehouse("_Test Storage General Zone", dc, is_group=1, nir_warehouse_role="Zone", nir_zone_type="General")
		cls.gen_bin = make_warehouse("_Test Storage General Bin", gen_zone, nir_warehouse_role="Bin")

		# Store warehouse directly under root
		cls.store_wh = make_warehouse("_Test Storage Store", root, nir_warehouse_role="Store")

		# Capacity bins
		cls.cap_bin = make_warehouse("_Test Storage Cap Bin", dc, nir_warehouse_role="Bin", nir_bin_capacity=100.0)
		cls.zero_cap_bin = make_warehouse("_Test Storage Zero Cap Bin", dc, nir_warehouse_role="Bin", nir_bin_capacity=0.0)

	def assertStorageBlocked(self, doc):
		with self.assertRaises(frappe.ValidationError):
			validate_storage(doc)

	def assertCapacityBlocked(self, doc):
		with self.assertRaises(frappe.ValidationError):
			validate_bin_capacity(doc)

	def test_below_25c_item_into_2_8c_allowed(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": BELOW_25C_ITEM, "warehouse": self.cold_bin}],
		})
		validate_storage(pr)

	def test_below_25c_item_into_below_25c_allowed(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": BELOW_25C_ITEM, "warehouse": self.cool_bin}],
		})
		validate_storage(pr)

	def test_below_25c_item_into_ambient_blocked(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": BELOW_25C_ITEM, "warehouse": self.ambient_bin}],
		})
		self.assertStorageBlocked(pr)

	def test_2_8c_item_into_ambient_blocked(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": COLD_ITEM, "warehouse": self.ambient_bin}],
		})
		self.assertStorageBlocked(pr)

	def test_2_8c_item_into_below_25c_blocked(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": COLD_ITEM, "warehouse": self.cool_bin}],
		})
		self.assertStorageBlocked(pr)

	def test_2_8c_item_into_2_8c_allowed(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": COLD_ITEM, "warehouse": self.cold_bin}],
		})
		validate_storage(pr)

	def test_warehouse_with_no_condition_treated_as_ambient(self):
		# Ambient into unconditioned warehouse is allowed
		pr_amb = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.unspec_bin}],
		})
		validate_storage(pr_amb)

		# Below 25C into unconditioned warehouse (treated as Ambient) is blocked
		pr_below = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": BELOW_25C_ITEM, "warehouse": self.unspec_bin}],
		})
		self.assertStorageBlocked(pr_below)

	def test_ambient_item_into_any_condition_allowed(self):
		for wh in (self.cold_bin, self.cool_bin, self.ambient_bin, self.unspec_bin):
			pr = frappe.get_doc({
				"doctype": "Purchase Receipt",
				"items": [{"item_code": AMBIENT_ITEM, "warehouse": wh}],
			})
			validate_storage(pr)

	def test_item_without_condition_skipped(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": NO_COND_ITEM, "warehouse": self.cold_bin}],
		})
		validate_storage(pr)

	def test_schedule_x_into_general_bin_blocked(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": SCHED_X_ITEM, "warehouse": self.gen_bin}],
		})
		self.assertStorageBlocked(pr)

	def test_schedule_x_into_cage_bin_allowed(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": SCHED_X_ITEM, "warehouse": self.cage_bin}],
		})
		validate_storage(pr)

	def test_schedule_x_into_store_allowed(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": SCHED_X_ITEM, "warehouse": self.store_wh}],
		})
		validate_storage(pr)

	def test_ndps_into_general_bin_blocked_and_cage_allowed(self):
		pr_fail = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": NDPS_ITEM, "warehouse": self.gen_bin}],
		})
		self.assertStorageBlocked(pr_fail)

		pr_pass = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": NDPS_ITEM, "warehouse": self.cage_bin}],
		})
		validate_storage(pr_pass)

	def test_storage_doctype_variations(self):
		# Purchase Invoice with update_stock=1
		pi_update = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"update_stock": 1,
			"items": [{"item_code": COLD_ITEM, "warehouse": self.ambient_bin}],
		})
		self.assertStorageBlocked(pi_update)

		# Purchase Invoice with update_stock=0 not checked
		pi_no_update = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"update_stock": 0,
			"items": [{"item_code": COLD_ITEM, "warehouse": self.ambient_bin}],
		})
		validate_storage(pi_no_update)

		# Stock Entry uses t_warehouse
		se = frappe.get_doc({
			"doctype": "Stock Entry",
			"purpose": "Material Transfer",
			"items": [{"item_code": COLD_ITEM, "s_warehouse": self.cold_bin, "t_warehouse": self.ambient_bin}],
		})
		self.assertStorageBlocked(se)

		# Stock Reconciliation uses warehouse
		sr = frappe.get_doc({
			"doctype": "Stock Reconciliation",
			"items": [{"item_code": COLD_ITEM, "warehouse": self.ambient_bin}],
		})
		self.assertStorageBlocked(sr)

	def test_storage_return_exempt(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"is_return": 1,
			"items": [{"item_code": COLD_ITEM, "warehouse": self.ambient_bin}],
		})
		validate_storage(pr)

	def test_bin_capacity_exceeded_blocked(self):
		# Create Bin record with current actual_qty = 60
		bin_doc = frappe.get_doc({
			"doctype": "Bin",
			"warehouse": self.cap_bin,
			"item_code": AMBIENT_ITEM,
			"actual_qty": 60,
		}).insert()
		self.addCleanup(frappe.db.delete, "Bin", {"name": bin_doc.name})

		# Incoming 50 + current 60 = 110 > capacity 100 -> BLOCKED
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "stock_qty": 50}],
		})
		self.assertCapacityBlocked(pr)

	def test_bin_capacity_at_exactly_capacity_allowed(self):
		bin_doc = frappe.get_doc({
			"doctype": "Bin",
			"warehouse": self.cap_bin,
			"item_code": AMBIENT_ITEM,
			"actual_qty": 50,
		}).insert()
		self.addCleanup(frappe.db.delete, "Bin", {"name": bin_doc.name})

		# Incoming 50 + current 50 = 100 == capacity 100 -> ALLOWED
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "stock_qty": 50}],
		})
		validate_bin_capacity(pr)

	def test_bin_capacity_zero_not_checked(self):
		# Warehouse with capacity 0.0 -> incoming 500 is allowed
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.zero_cap_bin, "stock_qty": 500}],
		})
		validate_bin_capacity(pr)

	def test_bin_capacity_multi_rows_aggregated(self):
		# No existing stock, but two rows sum to 60 + 50 = 110 > 100
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"items": [
				{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "stock_qty": 60},
				{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "stock_qty": 50},
			],
		})
		self.assertCapacityBlocked(pr)

	def test_bin_capacity_return_exempt(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"is_return": 1,
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "stock_qty": 500}],
		})
		validate_bin_capacity(pr)

	def test_stock_reconciliation_replaces_current_qty(self):
		bin_doc = frappe.get_doc({
			"doctype": "Bin",
			"warehouse": self.cap_bin,
			"item_code": AMBIENT_ITEM,
			"actual_qty": 90,
		}).insert()
		self.addCleanup(frappe.db.delete, "Bin", {"name": bin_doc.name})

		# counting 90 on hand as 95 leaves 95 in a 100 bin, not 90 + 95
		validate_bin_capacity(frappe.get_doc({
			"doctype": "Stock Reconciliation",
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "qty": 95}],
		}))
		self.assertCapacityBlocked(frappe.get_doc({
			"doctype": "Stock Reconciliation",
			"items": [{"item_code": AMBIENT_ITEM, "warehouse": self.cap_bin, "qty": 101}],
		}))
