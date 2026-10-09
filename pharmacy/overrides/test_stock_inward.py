# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.tests.utils import make_test_item

ITEM = "_Test Pharmacy Inward Item"


def make_receipt(batch_no):
	company = frappe.db.get_value("Company", {})
	warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0})
	return frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": company,
			"items": [
				{
					"item_code": ITEM,
					"qty": 10,
					"t_warehouse": warehouse,
					"basic_rate": 5,
					"batch_no": batch_no,
					"use_serial_batch_fields": 1,
				}
			],
		}
	).insert()


def make_batch(supplier_batch_no, **kwargs):
	return frappe.get_doc(
		{
			"doctype": "Batch",
			"item": ITEM,
			"supplier_batch_no": supplier_batch_no,
			"expiry_date": add_days(today(), 365),
			**kwargs,
		}
	).insert()


class TestInwardBatches(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_test_item(ITEM)

	def test_receipt_blocked_for_batch_without_mrp(self):
		receipt = make_receipt(make_batch("IN-NO-MRP").name)
		with self.assertRaisesRegex(frappe.ValidationError, "IN-NO-MRP"):
			receipt.submit()

	def test_receipt_allowed_for_batch_with_mrp(self):
		receipt = make_receipt(make_batch("IN-MRP", nir_mrp=20).name)
		receipt.submit()
		self.assertEqual(receipt.docstatus, 1)
