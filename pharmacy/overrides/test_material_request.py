# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from pharmacy.overrides.material_request import approve_manual_store_indent
from pharmacy.tests.utils import make_test_item


class TestManualStoreIndent(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()

		# Setup Warehouses & Store
		self.dc_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Indent DC Warehouse",
			"nir_warehouse_role": "DC",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		self.store_wh = frappe.get_doc({
			"doctype": "Warehouse",
			"warehouse_name": "Test Koramangala Store Warehouse",
			"nir_warehouse_role": "Store",
			"company": "_Test Company",
		}).insert(ignore_if_duplicate=True)

		self.store = frappe.get_doc({
			"doctype": "Pharmacy Store",
			"store_name": "Test Koramangala Store",
			"warehouse": self.store_wh.name,
			"serving_warehouse": self.dc_wh.name,
			"nir_manual_indent_limit": 5000.0,
			"nir_approval_status": "Approved",
			"disabled": 0,
		}).insert(ignore_if_duplicate=True)

		self.item = make_test_item("_Test Manual Indent Item", nir_abc_class="A")

	def tearDown(self):
		frappe.db.rollback()

	def test_manual_indent_below_threshold_auto_approved(self):
		mr = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Material Transfer",
			"company": "_Test Company",
			"schedule_date": today(),
			"nir_indent_type": "Manual",
			"items": [
				{
					"item_code": self.item.name,
					"qty": 10.0,  # 10 * 100 = 1000 <= 5000 limit
					"rate": 100.0,
					"from_warehouse": self.dc_wh.name,
					"warehouse": self.store_wh.name,
					"schedule_date": today(),
				}
			],
		}).insert()

		self.assertEqual(mr.nir_requires_area_manager_approval, 0)
		self.assertEqual(mr.nir_area_manager_approval_status, "Approved")

		# Submit allowed
		mr.submit()
		self.assertEqual(mr.docstatus, 1)

	def test_manual_indent_above_threshold_requires_area_manager_approval(self):
		mr = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Material Transfer",
			"company": "_Test Company",
			"schedule_date": today(),
			"nir_indent_type": "Manual",
			"items": [
				{
					"item_code": self.item.name,
					"qty": 100.0,  # 100 * 100 = 10,000 > 5,000 limit
					"rate": 100.0,
					"from_warehouse": self.dc_wh.name,
					"warehouse": self.store_wh.name,
					"schedule_date": today(),
				}
			],
		}).insert()

		self.assertEqual(mr.nir_requires_area_manager_approval, 1)
		self.assertEqual(mr.nir_area_manager_approval_status, "Pending Approval")

		# Submission before approval must fail
		with self.assertRaises(frappe.ValidationError):
			mr.submit()

		# Approve via Area Manager approval hook
		approve_res = approve_manual_store_indent(mr.name)
		self.assertEqual(approve_res["approval_status"], "Approved")

		mr.reload()
		self.assertEqual(mr.nir_area_manager_approval_status, "Approved")

		# Now submission succeeds
		mr.submit()
		self.assertEqual(mr.docstatus, 1)
