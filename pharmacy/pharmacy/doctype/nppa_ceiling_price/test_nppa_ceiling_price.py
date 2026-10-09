# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from pharmacy.pharmacy.doctype.nppa_ceiling_price.nppa_ceiling_price import get_active_ceiling_price
from pharmacy.tests.utils import make_test_item

IGNORE_TEST_RECORD_DEPENDENCIES = ["Item", "UOM"]

ITEM = "_Test NPPA Item"


def make_ceiling(valid_from, valid_upto=None, ceiling_price=1.5, item=ITEM):
	return frappe.get_doc(
		{
			"doctype": "NPPA Ceiling Price",
			"item": item,
			"ceiling_price": ceiling_price,
			"valid_from": valid_from,
			"valid_upto": valid_upto,
		}
	).insert()


class TestNPPACeilingPrice(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_test_item(ITEM)

	def tearDown(self):
		frappe.db.delete("NPPA Ceiling Price", {"item": ITEM})

	def test_valid_upto_before_from(self):
		with self.assertRaises(frappe.ValidationError):
			make_ceiling("2026-04-01", "2026-03-31")

	def test_consecutive_periods_allowed(self):
		make_ceiling("2025-04-01", "2026-03-31")
		make_ceiling("2026-04-01")

	def test_overlap_with_open_ended_period_rejected(self):
		make_ceiling("2025-04-01")
		with self.assertRaises(frappe.ValidationError):
			make_ceiling("2026-04-01", "2027-03-31")

	def test_open_ended_overlapping_later_period_rejected(self):
		make_ceiling("2026-04-01", "2027-03-31")
		with self.assertRaises(frappe.ValidationError):
			make_ceiling("2025-04-01")

	def test_get_active_ceiling_price(self):
		make_ceiling("2025-04-01", "2026-03-31", ceiling_price=2.0)
		make_ceiling("2026-04-01", ceiling_price=2.5)

		self.assertEqual(get_active_ceiling_price(ITEM, on_date="2025-06-01"), 2.0)
		self.assertEqual(get_active_ceiling_price(ITEM, on_date="2026-06-01"), 2.5)
		self.assertIsNone(get_active_ceiling_price(ITEM, on_date="2024-01-01"))
