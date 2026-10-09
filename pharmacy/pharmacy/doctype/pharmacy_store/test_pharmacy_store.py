# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from pharmacy.pharmacy.doctype.pharmacy_store.pharmacy_store import get_serving_store


class TestPharmacyStore(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_create_pharmacy_store_and_lookup(self):
		# Setup warehouses
		dc_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Regional DC Store WH",
			"nir_warehouse_role": "DC",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		store_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Retail Store WH 101",
			"nir_warehouse_role": "Store",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		# Setup Cluster
		cluster = frappe.get_doc({
			"doctype": "Cluster",
			"cluster_name": "Test South Zone Cluster",
			"description": "South Region Cluster",
		}).insert(ignore_if_duplicate=True)

		# Setup Drug Licence
		licence = frappe.get_doc({
			"doctype": "Drug Licence",
			"party_type": "Warehouse",
			"party": store_wh.name,
			"licence_no": "DL-STORE-101-2026",
			"licence_form": "20",
			"valid_from": "2025-01-01",
			"valid_upto": "2030-12-31",
		}).insert(ignore_if_duplicate=True)

		# Create Store Master (Pre-approved)
		store = frappe.get_doc({
			"doctype": "Pharmacy Store",
			"store_name": "Test Koramangala Store",
			"warehouse": store_wh.name,
			"serving_warehouse": dc_wh.name,
			"cluster": cluster.name,
			"route": "Route 5B - South Express",
			"store_grade": "A",
			"drug_licence": licence.name,
			"gstin": "29ABCDE1234F1Z5",
			"nir_approval_status": "Approved",
			"disabled": 0,
			"pincodes_served": [
				{"pincode": "560034", "delivery_type": "Same Day", "is_active": 1},
				{"pincode": "560095", "delivery_type": "Express 2hr", "is_active": 1},
			],
		}).insert()

		self.assertEqual(store.store_name, "Test Koramangala Store")
		self.assertEqual(store.store_grade, "A")
		self.assertEqual(len(store.pincodes_served), 2)

		# Test lookup function
		serving = get_serving_store("560034")
		self.assertIsNotNone(serving)
		self.assertEqual(serving.name, store.name)
		self.assertEqual(serving.delivery_type, "Same Day")

		# Lookup non-existent pincode
		self.assertIsNone(get_serving_store("999999"))

	def test_duplicate_pincode_validation(self):
		store = frappe.get_doc({
			"doctype": "Pharmacy Store",
			"store_name": "Test Dup Pincode Store",
			"warehouse": "Stores - _TC",
			"serving_warehouse": "Stores - _TC",
			"store_grade": "B",
			"nir_approval_status": "Approved",
			"disabled": 0,
			"pincodes_served": [
				{"pincode": "560001", "delivery_type": "Standard", "is_active": 1},
				{"pincode": "560001", "delivery_type": "Express 2hr", "is_active": 1},
			],
		})

		self.assertRaises(frappe.ValidationError, store.insert)
