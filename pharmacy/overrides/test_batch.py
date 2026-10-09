# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.tests.utils import make_test_item

ITEM = "_Test Pharmacy Batch Item"
NPPA_ITEM = "_Test Pharmacy NPPA Item"
PACK_ITEM = "_Test Pharmacy NPPA Strip Item"


def make_batch(**kwargs):
	defaults = {
		"doctype": "Batch",
		"item": ITEM,
		"nir_mrp": 100.0,
		"expiry_date": add_days(today(), 365),
	}
	defaults.update(kwargs)
	return frappe.get_doc(defaults).insert()


class TestBatchRules(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_test_item(ITEM, has_batch_no=1)
		make_test_item(NPPA_ITEM, has_batch_no=1, nir_nppa_controlled=1)
		gst_5 = frappe.db.get_value("Item Tax Template", {"gst_rate": 5, "disabled": 0})
		make_test_item(
			PACK_ITEM,
			nir_nppa_controlled=1,
			sales_uom="Strip",
			uoms=[{"uom": "Nos", "conversion_factor": 1}, {"uom": "Strip", "conversion_factor": 10}],
			taxes=[{"item_tax_template": gst_5}],
		)

	def tearDown(self):
		frappe.db.delete("Batch", {"item": ("in", [ITEM, NPPA_ITEM, PACK_ITEM])})
		frappe.db.delete("NPPA Ceiling Price", {"item": ("in", [NPPA_ITEM, PACK_ITEM])})

	def test_named_from_supplier_batch(self):
		batch = make_batch(supplier_batch_no=" AB123 ")
		self.assertEqual(batch.name, f"{ITEM}-AB123")

	def test_duplicate_supplier_batch_rejected(self):
		make_batch(supplier_batch_no="DUP1")
		with self.assertRaises(frappe.DuplicateEntryError):
			make_batch(supplier_batch_no="DUP1")

	def test_given_batch_id_kept_and_recorded(self):
		batch = make_batch(batch_id="RCPT-001")
		self.assertEqual(batch.name, "RCPT-001")
		self.assertEqual(batch.supplier_batch_no, "RCPT-001")

	def test_batch_without_mrp_can_be_saved(self):
		# ERPNext creates batches mid-receipt with only the item; MRP is checked on receipt instead
		batch = make_batch(nir_mrp=None, supplier_batch_no="NO-MRP")
		self.assertFalse(batch.nir_mrp)

	def test_mrp_uom_defaults_to_sales_uom(self):
		batch = make_batch(item=PACK_ITEM, nir_mrp=10, supplier_batch_no="UOM-DEFAULT")
		self.assertEqual(batch.nir_mrp_uom, "Strip")

	def test_nppa_ceiling_exceeded_rejected(self):
		frappe.get_doc(
			{
				"doctype": "NPPA Ceiling Price",
				"item": NPPA_ITEM,
				"ceiling_price": 50.0,
				"valid_from": add_days(today(), -10),
			}
		).insert()

		# Batch MRP 60.0 > ceiling 50.0 must be rejected
		with self.assertRaises(frappe.ValidationError):
			make_batch(item=NPPA_ITEM, nir_mrp=60.0, supplier_batch_no="NPPA-EXCEED")

	def test_nppa_ceiling_within_limit_allowed(self):
		frappe.get_doc(
			{
				"doctype": "NPPA Ceiling Price",
				"item": NPPA_ITEM,
				"ceiling_price": 50.0,
				"valid_from": add_days(today(), -10),
			}
		).insert()

		batch = make_batch(item=NPPA_ITEM, nir_mrp=45.0, supplier_batch_no="NPPA-OK")
		self.assertEqual(batch.nir_mrp, 45.0)

	def test_nppa_limit_scales_with_pack_and_gst(self):
		# 2.00 per tablet x 10 per strip + 5% GST = 21.00 per strip
		make_ceiling(PACK_ITEM, 2.0, add_days(today(), -10))

		batch = make_batch(item=PACK_ITEM, nir_mrp=21.0, supplier_batch_no="PACK-OK")
		self.assertEqual(batch.nir_mrp_uom, "Strip")

		with self.assertRaises(frappe.ValidationError):
			make_batch(item=PACK_ITEM, nir_mrp=21.01, supplier_batch_no="PACK-OVER")

	def test_nppa_limit_uses_ceiling_on_manufacturing_date(self):
		make_ceiling(PACK_ITEM, 3.0, add_days(today(), -400), add_days(today(), -31))
		make_ceiling(PACK_ITEM, 2.0, add_days(today(), -30))

		# 25 per strip is within the old ceiling (31.50) but over the current one (21.00)
		make_batch(item=PACK_ITEM, nir_mrp=25.0, manufacturing_date=add_days(today(), -60), supplier_batch_no="OLD")
		with self.assertRaises(frappe.ValidationError):
			make_batch(item=PACK_ITEM, nir_mrp=25.0, manufacturing_date=add_days(today(), -5), supplier_batch_no="NEW")


def make_ceiling(item, ceiling_price, valid_from, valid_upto=None):
	frappe.get_doc(
		{
			"doctype": "NPPA Ceiling Price",
			"item": item,
			"ceiling_price": ceiling_price,
			"valid_from": valid_from,
			"valid_upto": valid_upto,
		}
	).insert()
