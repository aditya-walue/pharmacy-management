# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from pharmacy.pharmacy.replenishment import (
	create_delivery_from_indent,
	create_replenishment_material_request,
	generate_replenishment_suggestions,
)
from pharmacy.tests.utils import make_test_item


class TestReplenishment(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_generate_replenishment_suggestions_and_material_request(self):
		# Setup Warehouses
		dc_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Main DC Warehouse",
			"nir_warehouse_role": "DC",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		store_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Whitefield Store Warehouse",
			"nir_warehouse_role": "Store",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		# Setup Store
		store = frappe.get_doc({
			"doctype": "Pharmacy Store",
			"store_name": "Test Whitefield Store",
			"warehouse": store_wh.name,
			"serving_warehouse": dc_wh.name,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		# Create Test Item
		item = make_test_item("_Test Replenishment Item 99", nir_abc_class="A")

		# Create Replenishment Schedule for Item & Store (Reorder Level: 20, Reorder Qty: 100)
		frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Test Whitefield Item Sched",
			"scope": "Store",
			"store": store.name,
			"applies_to": "Item",
			"item": item.name,
			"frequency": "Daily",
			"order_days": "Daily",
			"reorder_level": 20.0,
			"reorder_qty": 100.0,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		# Generate Suggestions
		suggestions = generate_replenishment_suggestions(store=store.name)
		self.assertTrue(len(suggestions) >= 1)

		item_sugg = next(s for s in suggestions if s["item_code"] == item.name)
		self.assertEqual(item_sugg["suggested_action"], "Reorder")
		self.assertEqual(item_sugg["suggested_qty"], 120.0)
		self.assertEqual(item_sugg["serving_warehouse"], dc_wh.name)

		# Test Material Request Auto-Creation
		mr_result = create_replenishment_material_request(store=store.name, items=[item.name])
		self.assertIsNotNone(mr_result)
		self.assertTrue(mr_result["items_count"] >= 1)

		mr_doc = frappe.get_doc("Material Request", mr_result["name"])
		self.assertEqual(mr_doc.material_request_type, "Material Transfer")
		self.assertEqual(mr_doc.items[0].from_warehouse, dc_wh.name)
		self.assertEqual(mr_doc.items[0].warehouse, store_wh.name)

	def test_single_indent_and_single_delivery(self):
		dc_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Main DC Warehouse 2",
			"nir_warehouse_role": "DC",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		store_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Indira Store Warehouse",
			"nir_warehouse_role": "Store",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		store = frappe.get_doc({
			"doctype": "Pharmacy Store",
			"store_name": "Test Indira Store",
			"warehouse": store_wh.name,
			"serving_warehouse": dc_wh.name,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		item1 = make_test_item("_Test Indent Item 1", nir_abc_class="A")
		item2 = make_test_item("_Test Indent Item 2", nir_abc_class="B")

		# Create schedule for both items due daily
		frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Test Indent Item 1 Sched",
			"scope": "Store",
			"store": store.name,
			"applies_to": "Item",
			"item": item1.name,
			"frequency": "Daily",
			"reorder_level": 10.0,
			"reorder_qty": 50.0,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Test Indent Item 2 Sched",
			"scope": "Store",
			"store": store.name,
			"applies_to": "Item",
			"item": item2.name,
			"frequency": "Daily",
			"reorder_level": 10.0,
			"reorder_qty": 50.0,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		# Create indent (Material Request) for store
		mr_res = create_replenishment_material_request(store=store.name, items=[item1.name, item2.name])
		self.assertIsNotNone(mr_res)
		mr_name = mr_res["name"]

		# Verify all due items for this store go into ONE single indent
		mr_doc = frappe.get_doc("Material Request", mr_name)
		item_codes = [d.item_code for d in mr_doc.items]
		self.assertIn(item1.name, item_codes)
		self.assertIn(item2.name, item_codes)

		# Create delivery (Stock Entry) from indent
		del_res = create_delivery_from_indent(mr_name)
		self.assertIsNotNone(del_res)

		# Verify all items from indent go into ONE single delivery document
		se_doc = frappe.get_doc("Stock Entry", del_res["name"])
		self.assertEqual(se_doc.purpose, "Material Transfer")
		se_item_codes = [d.item_code for d in se_doc.items]
		self.assertIn(item1.name, se_item_codes)
		self.assertIn(item2.name, se_item_codes)

