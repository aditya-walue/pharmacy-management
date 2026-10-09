# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

IGNORE_TEST_RECORD_DEPENDENCIES = ["Item", "Item Group"]

ITEM_GROUP = "_Test Shelf Life Group"


def make_rule(**kwargs):
	defaults = {
		"doctype": "Shelf Life Rule",
		"applies_to": "Item Group",
		"item_group": ITEM_GROUP,
		"min_days_supplier_receipt": 180,
		"min_days_store_dispatch": 90,
	}
	defaults.update(kwargs)
	return frappe.get_doc(defaults).insert()


class TestShelfLifeRule(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Item Group", ITEM_GROUP):
			root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("is", "not set")})
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": root}
			).insert()

	def tearDown(self):
		frappe.db.delete("Shelf Life Rule", {"item_group": ITEM_GROUP})
		frappe.db.delete("Shelf Life Rule", {"regulatory_category": "Schedule H1"})

	def test_unused_target_cleared(self):
		rule = make_rule(regulatory_category="Schedule H1")
		self.assertIsNone(rule.regulatory_category)

	def test_regulatory_category_rule_created(self):
		rule = make_rule(
			applies_to="Regulatory Category",
			regulatory_category="Schedule H1",
			item_group=None,
		)
		self.assertEqual(rule.applies_to, "Regulatory Category")
		self.assertEqual(rule.regulatory_category, "Schedule H1")
		self.assertIsNone(rule.item_group)

	def test_duplicate_active_rule_rejected(self):
		make_rule()
		with self.assertRaises(frappe.DuplicateEntryError):
			make_rule()

	def test_disabled_rule_allowed_alongside_active(self):
		make_rule()
		make_rule(disabled=1)
