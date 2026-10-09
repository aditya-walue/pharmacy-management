# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.overrides.shelf_life import validate_shelf_life
from pharmacy.tests.utils import make_test_item

ITEM_CAT = "_Test SL Cat Item"
ITEM_GROUP = "_Test SL Group Item"
ITEM_DUAL = "_Test SL Dual Item"
ITEM_NO_RULE = "_Test SL No Rule Item"
ITEM_CHILD = "_Test SL Child Group Item"
ITEM_LEAF = "_Test SL Leaf Group Item"

PARENT_GROUP = "_Test SL Parent Group"
CHILD_GROUP = "_Test SL Child Group"
LEAF_GROUP = "_Test SL Leaf Group"


def make_warehouse(name, parent=None, is_group=0, **kwargs):
	company = frappe.db.get_value("Company", {})
	abbr = frappe.db.get_value("Company", company, "abbr")
	full_name = f"{name} - {abbr}"
	if not frappe.db.exists("Warehouse", full_name):
		root = parent or frappe.db.get_value("Warehouse", {"is_group": 1, "parent_warehouse": ("is", "not set")})
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": name,
				"company": company,
				"parent_warehouse": root,
				"is_group": is_group,
				**kwargs,
			}
		).insert()
		return doc.name
	return full_name


def make_item_group(name, parent):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": parent,
				"is_group": 1,
			}
		).insert()
	return name


def make_batch(item, expiry_date, supplier_batch_no, nir_mrp=100.0):
	return frappe.get_doc(
		{
			"doctype": "Batch",
			"item": item,
			"supplier_batch_no": supplier_batch_no,
			"expiry_date": expiry_date,
			"nir_mrp": nir_mrp,
		}
	).insert()


def make_rule(applies_to, target, receipt_days, dispatch_days, disabled=0):
	field = "regulatory_category" if applies_to == "Regulatory Category" else "item_group"
	doc = frappe.get_doc(
		{
			"doctype": "Shelf Life Rule",
			"applies_to": applies_to,
			field: target,
			"min_days_supplier_receipt": receipt_days,
			"min_days_store_dispatch": dispatch_days,
			"disabled": disabled,
		}
	).insert()
	return doc


class TestShelfLife(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		root_group = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("is", "not set")})
		make_item_group(PARENT_GROUP, root_group)
		make_item_group(CHILD_GROUP, PARENT_GROUP)
		make_item_group(LEAF_GROUP, CHILD_GROUP)

		make_test_item(ITEM_CAT, nir_regulatory_category="Schedule H", item_group=root_group)
		make_test_item(ITEM_GROUP, nir_regulatory_category="Cosmetic", item_group=PARENT_GROUP)
		make_test_item(ITEM_DUAL, nir_regulatory_category="Schedule H1", item_group=PARENT_GROUP)
		make_test_item(ITEM_NO_RULE, nir_regulatory_category="Cosmetic", item_group=root_group)
		make_test_item(ITEM_CHILD, nir_regulatory_category="Cosmetic", item_group=CHILD_GROUP)
		make_test_item(ITEM_LEAF, nir_regulatory_category="Cosmetic", item_group=LEAF_GROUP)

		root_wh = frappe.db.get_value("Warehouse", {"is_group": 1, "parent_warehouse": ("is", "not set")})
		cls.dc_bin = make_warehouse("_Test SL DC Bin", root_wh, nir_warehouse_role="Bin")
		cls.store_wh = make_warehouse("_Test SL Store WH", root_wh, nir_warehouse_role="Store")

		cls.rules = [
			make_rule("Regulatory Category", "Schedule H", receipt_days=180, dispatch_days=60),
			make_rule("Item Group", PARENT_GROUP, receipt_days=120, dispatch_days=90),
			make_rule("Regulatory Category", "Schedule H1", receipt_days=180, dispatch_days=60),
			make_rule("Item Group", CHILD_GROUP, receipt_days=200, dispatch_days=100),
		]

		cls.batch_10d = make_batch(ITEM_CAT, add_days(today(), 10), "SL-10D").name
		cls.batch_70d = make_batch(ITEM_DUAL, add_days(today(), 70), "SL-70D").name
		cls.batch_150d = make_batch(ITEM_DUAL, add_days(today(), 150), "SL-150D").name
		cls.batch_250d = make_batch(ITEM_DUAL, add_days(today(), 250), "SL-250D").name
		cls.batch_child_160d = make_batch(ITEM_CHILD, add_days(today(), 160), "SL-CH-160D").name
		cls.batch_leaf_110d = make_batch(ITEM_LEAF, add_days(today(), 110), "SL-LF-110D").name
		cls.batch_leaf_130d = make_batch(ITEM_LEAF, add_days(today(), 130), "SL-LF-130D").name
		cls.batch_no_expiry = make_batch(ITEM_CAT, add_days(today(), 365), "SL-NO-EXP").name
		frappe.db.set_value("Batch", cls.batch_no_expiry, "expiry_date", None)

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		for r in cls.rules:
			frappe.db.delete("Shelf Life Rule", {"name": r.name})
		frappe.db.delete("Batch", {"name": ("in", [
			cls.batch_10d, cls.batch_70d, cls.batch_150d, cls.batch_250d,
			cls.batch_child_160d, cls.batch_leaf_110d, cls.batch_leaf_130d, cls.batch_no_expiry,
		])})

	def assertBlocked(self, doc):
		with self.assertRaises(frappe.ValidationError):
			validate_shelf_life(doc)

	def test_purchase_receipt_insufficient_shelf_life_blocked(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		self.assertBlocked(pr)

	def test_purchase_receipt_sufficient_shelf_life_allowed(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": self.batch_250d}],
		})
		validate_shelf_life(pr)

	def test_stricter_rule_wins_on_receipt(self):
		# ITEM_DUAL: Category rule requires 180, Group rule requires 120 -> stricter is 180
		# batch_150d has 150 days remaining: > 120 but < 180 -> must block!
		pr_fail = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_DUAL, "warehouse": self.dc_bin, "batch_no": self.batch_150d}],
		})
		self.assertBlocked(pr_fail)

		# batch_250d has 250 days remaining: > 180 -> passes!
		pr_pass = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_DUAL, "warehouse": self.dc_bin, "batch_no": self.batch_250d}],
		})
		validate_shelf_life(pr_pass)

	def test_stricter_rule_wins_on_dispatch(self):
		# ITEM_DUAL: Category rule requires 60, Group rule requires 90 -> stricter is 90
		# batch_70d has 70 days remaining: > 60 but < 90 -> must block!
		dn_fail = frappe.get_doc({
			"doctype": "Delivery Note",
			"is_internal_customer": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_DUAL, "warehouse": self.store_wh, "batch_no": self.batch_70d}],
		})
		self.assertBlocked(dn_fail)

		# batch_150d has 150 days remaining: > 90 -> passes!
		dn_pass = frappe.get_doc({
			"doctype": "Delivery Note",
			"is_internal_customer": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_DUAL, "warehouse": self.store_wh, "batch_no": self.batch_150d}],
		})
		validate_shelf_life(dn_pass)

	def test_nearest_ancestor_item_group_rule_used(self):
		# ITEM_CHILD is in CHILD_GROUP (rule: receipt 200). 160d is < 200 -> blocks!
		pr_child = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CHILD, "warehouse": self.dc_bin, "batch_no": self.batch_child_160d}],
		})
		self.assertBlocked(pr_child)

		# ITEM_LEAF is in LEAF_GROUP (no rule). Nearest ancestor is CHILD_GROUP (rule: receipt 200).
		# batch_leaf_110d has 110 days: < 200 -> blocks!
		pr_leaf_fail = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_LEAF, "warehouse": self.dc_bin, "batch_no": self.batch_leaf_110d}],
		})
		self.assertBlocked(pr_leaf_fail)

	def test_receipt_vs_dispatch_threshold_picked_correctly(self):
		# ITEM_CAT has Category rule: receipt 180, dispatch 60.
		# A batch with 70 days remaining: fails receipt (< 180), passes dispatch (> 60).
		batch_70d = self.batch_70d
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": batch_70d}],
		})
		self.assertBlocked(pr)

		dn = frappe.get_doc({
			"doctype": "Delivery Note",
			"is_internal_customer": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.store_wh, "batch_no": batch_70d}],
		})
		validate_shelf_life(dn)

	def test_material_transfer_to_non_store_not_checked(self):
		# Transfer into dc_bin (role Bin, not Store) -> not checked for dispatch
		se = frappe.get_doc({
			"doctype": "Stock Entry",
			"purpose": "Material Transfer",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "s_warehouse": self.store_wh, "t_warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		validate_shelf_life(se)

	def test_material_transfer_to_store_checked_for_dispatch(self):
		# Transfer into store_wh (role Store) -> checked for dispatch (needs 60 days, has 10)
		se = frappe.get_doc({
			"doctype": "Stock Entry",
			"purpose": "Material Transfer",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "s_warehouse": self.dc_bin, "t_warehouse": self.store_wh, "batch_no": self.batch_10d}],
		})
		self.assertBlocked(se)

	def test_purchase_invoice_update_stock_flag(self):
		pi_update = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"update_stock": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		self.assertBlocked(pi_update)

		pi_no_update = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"update_stock": 0,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		validate_shelf_life(pi_no_update)

	def test_sales_invoice_update_stock_flag(self):
		si_update = frappe.get_doc({
			"doctype": "Sales Invoice",
			"is_internal_customer": 1,
			"update_stock": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.store_wh, "batch_no": self.batch_10d}],
		})
		self.assertBlocked(si_update)

		si_no_update = frappe.get_doc({
			"doctype": "Sales Invoice",
			"update_stock": 0,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.store_wh, "batch_no": self.batch_10d}],
		})
		validate_shelf_life(si_no_update)

	def test_counter_and_customer_sales_not_checked(self):
		# stores sell short-dated stock to consumers; the dispatch rule only governs stock sent to stores
		for doctype in ("POS Invoice", "Sales Invoice", "Delivery Note"):
			doc = frappe.get_doc({
				"doctype": doctype,
				"update_stock": 1,
				"posting_date": today(),
				"items": [{"item_code": ITEM_CAT, "warehouse": self.store_wh, "batch_no": self.batch_10d}],
			})
			validate_shelf_life(doc)

	def test_material_receipt_checked_for_receipt(self):
		se_receipt = frappe.get_doc({
			"doctype": "Stock Entry",
			"purpose": "Material Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "t_warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		self.assertBlocked(se_receipt)

	def test_return_and_consolidated_exempt(self):
		pr_ret = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"is_return": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		validate_shelf_life(pr_ret)

		si_cons = frappe.get_doc({
			"doctype": "Sales Invoice",
			"is_consolidated": 1,
			"update_stock": 1,
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.store_wh, "batch_no": self.batch_10d}],
		})
		validate_shelf_life(si_cons)

	def test_batch_without_expiry_skipped(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_CAT, "warehouse": self.dc_bin, "batch_no": self.batch_no_expiry}],
		})
		validate_shelf_life(pr)

	def test_item_without_rule_skipped(self):
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt",
			"posting_date": today(),
			"items": [{"item_code": ITEM_NO_RULE, "warehouse": self.dc_bin, "batch_no": self.batch_10d}],
		})
		validate_shelf_life(pr)
