# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

MAKER = "_test_maker@example.com"
CHECKER = "_test_checker@example.com"


def create_user_if_not_exists(email, role="System Manager"):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		return user.name
	return email


class TestMakerChecker(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.maker_user = create_user_if_not_exists(MAKER)
		cls.checker_user = create_user_if_not_exists(CHECKER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Item", {"item_code": ("like", "_Test MC Item%")})
		frappe.db.delete("Supplier", {"supplier_name": ("like", "_Test MC Supplier%")})
		frappe.db.delete("Customer", {"customer_name": ("like", "_Test MC Customer%")})
		frappe.db.delete("Batch", {"item": ("like", "_Test MC Item%")})
		frappe.db.delete("Item Price", {"item_code": ("like", "_Test MC Item%")})
		frappe.db.delete("Replenishment Schedule", {"schedule_name": ("like", "_Test MC Schedule%")})

	def _get_item_group(self):
		return frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("is", "not set")})

	def test_new_item_created_pending_and_disabled(self):
		frappe.set_user(MAKER)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test MC Item 1",
				"item_group": self._get_item_group(),
				"stock_uom": "Nos",
				"gst_hsn_code": "30049099",
				"is_stock_item": 1,
				"nir_regulatory_category": "OTC",
				"nir_storage_condition": "Ambient",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(item.nir_approval_status, "Pending Approval")
		self.assertEqual(item.disabled, 1)
		self.assertEqual(item.nir_maker, MAKER)

	def test_maker_cannot_approve_own_item(self):
		frappe.set_user(MAKER)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test MC Item 2",
				"item_group": self._get_item_group(),
				"stock_uom": "Nos",
				"gst_hsn_code": "30049099",
				"is_stock_item": 1,
				"nir_regulatory_category": "OTC",
				"nir_storage_condition": "Ambient",
			}
		).insert(ignore_permissions=True)

		item.nir_approval_status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			item.save(ignore_permissions=True)

	def test_checker_can_approve_item(self):
		frappe.set_user(MAKER)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test MC Item 3",
				"item_group": self._get_item_group(),
				"stock_uom": "Nos",
				"gst_hsn_code": "30049099",
				"is_stock_item": 1,
				"nir_regulatory_category": "OTC",
				"nir_storage_condition": "Ambient",
			}
		).insert(ignore_permissions=True)

		frappe.set_user(CHECKER)
		item.nir_approval_status = "Approved"
		item.save(ignore_permissions=True)

		self.assertEqual(item.nir_approval_status, "Approved")
		self.assertEqual(item.disabled, 0)
		self.assertEqual(item.nir_approved_by, CHECKER)

	def test_editing_controlled_field_relocks_item(self):
		frappe.set_user(MAKER)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test MC Item 4",
				"item_group": self._get_item_group(),
				"stock_uom": "Nos",
				"gst_hsn_code": "30049099",
				"is_stock_item": 1,
				"nir_regulatory_category": "OTC",
				"nir_storage_condition": "Ambient",
			}
		).insert(ignore_permissions=True)

		frappe.set_user(CHECKER)
		item.nir_approval_status = "Approved"
		item.save(ignore_permissions=True)
		self.assertEqual(item.disabled, 0)

		# Edit controlled field regulatory category
		frappe.set_user(MAKER)
		item.nir_regulatory_category = "Schedule H"
		item.save(ignore_permissions=True)

		self.assertEqual(item.nir_approval_status, "Pending Approval")
		self.assertEqual(item.disabled, 1)

	def test_batch_mrp_change_requires_checker_approval(self):
		frappe.set_user(MAKER)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test MC Item 5",
				"item_group": self._get_item_group(),
				"stock_uom": "Nos",
				"gst_hsn_code": "30049099",
				"is_stock_item": 1,
				"nir_regulatory_category": "OTC",
				"nir_storage_condition": "Ambient",
				"nir_approval_status": "Approved",
				"disabled": 0,
			}
		).insert(ignore_permissions=True)

		batch = frappe.get_doc(
			{
				"doctype": "Batch",
				"item": item.name,
				"supplier_batch_no": "MC-B1",
				"nir_mrp": 100.0,
				"expiry_date": add_days(today(), 365),
				"nir_approval_status": "Approved",
			}
		).insert(ignore_permissions=True)

		# Maker updates MRP from 100 to 120
		frappe.set_user(MAKER)
		batch.nir_mrp = 120.0
		batch.save(ignore_permissions=True)

		# Old MRP stays active, new MRP is in pending_mrp
		self.assertEqual(batch.nir_mrp, 100.0)
		self.assertEqual(batch.nir_pending_mrp, 120.0)
		self.assertEqual(batch.nir_approval_status, "Pending Approval")

		# Maker self-approval fails
		batch.nir_approval_status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			batch.save(ignore_permissions=True)

		# Checker approves
		frappe.set_user(CHECKER)
		batch.reload()
		batch.nir_approval_status = "Approved"
		batch.save(ignore_permissions=True)

		self.assertEqual(batch.nir_mrp, 120.0)
		self.assertIsNone(batch.nir_pending_mrp)
		self.assertEqual(batch.nir_approval_status, "Approved")

	def test_item_price_change_requires_checker_approval(self):
		frappe.set_user(MAKER)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test MC Item 6",
				"item_group": self._get_item_group(),
				"stock_uom": "Nos",
				"gst_hsn_code": "30049099",
				"is_stock_item": 1,
				"nir_regulatory_category": "OTC",
				"nir_storage_condition": "Ambient",
				"nir_approval_status": "Approved",
				"disabled": 0,
			}
		).insert(ignore_permissions=True)

		price_list = frappe.db.get_value("Price List", {"selling": 1}) or "Standard Selling"
		item_price = frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item.name,
				"price_list": price_list,
				"price_list_rate": 50.0,
				"nir_approval_status": "Approved",
			}
		).insert(ignore_permissions=True)

		# Maker changes rate to 60.0
		frappe.set_user(MAKER)
		item_price.price_list_rate = 60.0
		item_price.save(ignore_permissions=True)

		self.assertEqual(item_price.price_list_rate, 50.0)
		self.assertEqual(item_price.nir_pending_rate, 60.0)
		self.assertEqual(item_price.nir_approval_status, "Pending Approval")

		# Checker approves
		frappe.set_user(CHECKER)
		item_price.reload()
		item_price.nir_approval_status = "Approved"
		item_price.save(ignore_permissions=True)

		self.assertEqual(item_price.price_list_rate, 60.0)
		self.assertIsNone(item_price.nir_pending_rate)
		self.assertEqual(item_price.nir_approval_status, "Approved")

	def test_supplier_maker_checker(self):
		frappe.set_user(MAKER)
		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "_Test MC Supplier 1",
				"supplier_type": "Company",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(supplier.nir_approval_status, "Pending Approval")
		self.assertEqual(supplier.disabled, 1)

		# Checker approves
		frappe.set_user(CHECKER)
		supplier.nir_approval_status = "Approved"
		supplier.save(ignore_permissions=True)

		self.assertEqual(supplier.nir_approval_status, "Approved")
		self.assertEqual(supplier.disabled, 0)

	def test_replenishment_schedule_maker_checker(self):
		frappe.set_user(MAKER)
		schedule = frappe.get_doc(
			{
				"doctype": "Replenishment Schedule",
				"schedule_name": "_Test MC Schedule 1",
				"scope": "All Stores",
				"applies_to": "Global",
				"frequency": "Daily",
				"reorder_level": 10,
				"reorder_qty": 50,
			}
		).insert(ignore_permissions=True)

		self.assertEqual(schedule.nir_approval_status, "Pending Approval")
		self.assertEqual(schedule.disabled, 1)

		# Checker approves
		frappe.set_user(CHECKER)
		schedule.nir_approval_status = "Approved"
		schedule.save(ignore_permissions=True)

		self.assertEqual(schedule.nir_approval_status, "Approved")
		self.assertEqual(schedule.disabled, 0)
