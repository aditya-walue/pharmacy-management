# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestItemRules(IntegrationTestCase):
	def tearDown(self):
		frappe.db.delete("Item", {"item_code": ("like", "_Test Item Rule%")})

	def _get_item_group(self):
		return frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("is", "not set")})

	def _make_item(self, **kwargs):
		defaults = {
			"doctype": "Item",
			"item_group": self._get_item_group(),
			"stock_uom": "Nos",
			"gst_hsn_code": "30049099",
			"is_stock_item": 1,
			"nir_regulatory_category": "OTC",
			"nir_storage_condition": "Ambient",
		}
		defaults.update(kwargs)
		return frappe.get_doc(defaults).insert()

	def test_stock_item_forces_batch_and_expiry(self):
		item = self._make_item(
			item_code="_Test Item Rule Batch Expiry",
			has_batch_no=0,
			has_expiry_date=0,
		)

		self.assertEqual(item.has_batch_no, 1)
		self.assertEqual(item.has_expiry_date, 1)
		self.assertEqual(item.create_new_batch, 0)

	def test_existing_item_batch_flags_left_alone(self):
		item = self._make_item(item_code="_Test Item Rule Existing")
		item.has_batch_no = 0
		item.has_expiry_date = 0
		item.save()
		self.assertEqual(item.has_batch_no, 0)
		self.assertEqual(item.has_expiry_date, 0)

	def test_regulatory_category_mandatory_for_stock_item(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_item(
				item_code="_Test Item Rule No Category",
				nir_regulatory_category="",
			)

	def test_storage_condition_mandatory_for_stock_item(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_item(
				item_code="_Test Item Rule No Storage",
				nir_storage_condition="",
			)

	def test_rx_required_autoset_for_scheduled_drugs(self):
		for cat in ["Schedule H", "Schedule H1", "Schedule X", "NDPS"]:
			item = self._make_item(
				item_code=f"_Test Item Rule {cat.replace(' ', '_')}",
				nir_regulatory_category=cat,
				nir_rx_required=0,
			)
			self.assertEqual(item.nir_rx_required, 1)

	def test_rx_not_set_for_otc_cosmetic_fssai(self):
		for cat in ["OTC", "Cosmetic", "FSSAI"]:
			item = self._make_item(
				item_code=f"_Test Item Rule {cat}",
				nir_regulatory_category=cat,
			)
			self.assertEqual(item.nir_rx_required, 0)
