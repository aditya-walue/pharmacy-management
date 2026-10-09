# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from pharmacy.pharmacy.doctype.replenishment_schedule.replenishment_schedule import (
	get_effective_replenishment_schedule,
)
from pharmacy.tests.utils import make_test_item


class TestReplenishmentSchedule(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_scope_and_applies_to_validation(self):
		# Cluster scope missing cluster link
		sched1 = frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Test Cluster Sched Missing Cluster",
			"scope": "Cluster",
			"applies_to": "Global",
			"reorder_level": 10,
			"reorder_qty": 50,
		})
		self.assertRaises(frappe.ValidationError, sched1.insert)

		# ABC Class applies_to missing abc_class
		sched2 = frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Test ABC Sched Missing ABC Class",
			"scope": "All Stores",
			"applies_to": "ABC Class",
			"reorder_level": 10,
			"reorder_qty": 50,
		})
		self.assertRaises(frappe.ValidationError, sched2.insert)

	def test_schedule_resolution_hierarchy(self):
		# Create Item with ABC Class A
		item = make_test_item("_Test Replenishment Item A", nir_abc_class="A")

		# Create Cluster & Store
		cluster = frappe.get_doc({
			"doctype": "Cluster",
			"cluster_name": "Test North Cluster",
		}).insert(ignore_if_duplicate=True)

		store_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Indiranagar Store WH",
			"nir_warehouse_role": "Store",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		store = frappe.get_doc({
			"doctype": "Pharmacy Store",
			"store_name": "Test Indiranagar Store",
			"warehouse": store_wh.name,
			"serving_warehouse": store_wh.name,
			"cluster": cluster.name,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		# 1. Global ABC Class A Schedule (Twice a Week)
		frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Global ABC-A Rule",
			"scope": "All Stores",
			"applies_to": "ABC Class",
			"abc_class": "A",
			"frequency": "Twice a Week",
			"order_days": "Monday & Thursday",
			"reorder_level": 100,
			"reorder_qty": 500,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert()

		res_global = get_effective_replenishment_schedule(item.name)
		self.assertEqual(res_global["frequency"], "Twice a Week")
		self.assertEqual(res_global["order_days"], "Monday & Thursday")
		self.assertEqual(res_global["reorder_level"], 100)

		# 2. Cluster Level Override for Item (Alternate Days)
		frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Cluster North Item Rule",
			"scope": "Cluster",
			"cluster": cluster.name,
			"applies_to": "Item",
			"item": item.name,
			"frequency": "Alternate Days",
			"order_days": "Mon, Wed, Fri",
			"reorder_level": 200,
			"reorder_qty": 800,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert()

		res_cluster = get_effective_replenishment_schedule(item.name, cluster=cluster.name)
		self.assertEqual(res_cluster["frequency"], "Alternate Days")
		self.assertEqual(res_cluster["order_days"], "Mon, Wed, Fri")
		self.assertEqual(res_cluster["reorder_level"], 200)

		# 3. Store Level Specific Override (Daily)
		frappe.get_doc({
			"doctype": "Replenishment Schedule",
			"schedule_name": "Indiranagar Store Specific Rule",
			"scope": "Store",
			"store": store.name,
			"applies_to": "Item",
			"item": item.name,
			"frequency": "Daily",
			"order_days": "Daily",
			"reorder_level": 300,
			"reorder_qty": 1000,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert()

		res_store = get_effective_replenishment_schedule(item.name, store=store.name)
		self.assertEqual(res_store["frequency"], "Daily")
		self.assertEqual(res_store["reorder_level"], 300)
		self.assertEqual(res_store["scope"], "Store")
