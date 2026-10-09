# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestSalt(IntegrationTestCase):
	def tearDown(self):
		frappe.db.delete("Salt", {"salt_name": ("like", "_Test Salt%")})

	def test_create_salt_with_strength_and_dosage(self):
		salt = frappe.get_doc(
			{
				"doctype": "Salt",
				"salt_name": "_Test Salt Paracetamol",
				"strength": "500 mg",
				"dosage_form": "Tablet",
			}
		).insert()
		self.assertEqual(salt.name, "_Test Salt Paracetamol")
		self.assertEqual(salt.strength, "500 mg")
		self.assertEqual(salt.dosage_form, "Tablet")

	def test_duplicate_salt_name_rejected(self):
		frappe.get_doc(
			{
				"doctype": "Salt",
				"salt_name": "_Test Salt Amoxicillin",
				"strength": "250 mg",
				"dosage_form": "Capsule",
			}
		).insert()

		with self.assertRaises((frappe.DuplicateEntryError, frappe.ValidationError)):
			frappe.get_doc(
				{
					"doctype": "Salt",
					"salt_name": "_Test Salt Amoxicillin",
					"strength": "500 mg",
					"dosage_form": "Tablet",
				}
			).insert()
