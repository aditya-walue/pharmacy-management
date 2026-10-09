# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


class TestSupplierMaster(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_supplier_master_fields_and_licence(self):
		# Create Supplier
		supplier = frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": "Test Medicos Pharma Ltd",
			"supplier_group": "All Supplier Groups",
			"supplier_type": "Company",
			"gstin": "29AABCS1429B1ZQ",
			"nir_fssai_no": "10020011000123",
			"nir_lead_time_days": 3,
			"nir_moq_value": 15000.0,
			"nir_moq_qty": 500.0,
			"nir_expiry_return_window_days": 90,
			"nir_expiry_credit_pct": 100.0,
			"nir_expiry_return_policy": "Full Credit Pre-Expiry",
			"nir_approval_status": "Approved",
		}).insert()

		self.assertEqual(supplier.nir_fssai_no, "10020011000123")
		self.assertEqual(supplier.nir_lead_time_days, 3)
		self.assertEqual(supplier.nir_moq_value, 15000.0)
		self.assertEqual(supplier.nir_expiry_return_policy, "Full Credit Pre-Expiry")

		# Create Wholesale Drug Licence for Supplier (20B / 21B)
		licence_20b = frappe.get_doc({
			"doctype": "Drug Licence",
			"party_type": "Supplier",
			"party": supplier.name,
			"licence_no": "KA-BLR-20B-998811",
			"licence_form": "20B",
			"valid_from": add_days(today(), -100),
			"valid_upto": add_days(today(), 365),
		}).insert()

		self.assertEqual(licence_20b.status, "Active")

		# Create FSSAI licence for Supplier
		licence_fssai = frappe.get_doc({
			"doctype": "Drug Licence",
			"party_type": "Supplier",
			"party": supplier.name,
			"licence_no": "FSSAI-SUP-12345",
			"licence_form": "FSSAI",
			"valid_from": add_days(today(), -100),
			"valid_upto": add_days(today(), 365),
		}).insert()

		self.assertEqual(licence_fssai.status, "Active")
