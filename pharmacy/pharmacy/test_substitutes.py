# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from pharmacy.pharmacy.substitutes import get_substitutes
from pharmacy.tests.utils import make_test_item

SALT = "_Test Substitute Salt"


class TestSubstitutes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Salt", SALT):
			frappe.get_doc({"doctype": "Salt", "salt_name": SALT}).insert()

		same = {"nir_salt": SALT, "nir_strength": "500 mg"}
		make_test_item("_Test Sub Brand A", item_name="A Brand", **same)
		make_test_item("_Test Sub Brand B", item_name="B Brand", **same)
		make_test_item("_Test Sub Own Label", item_name="Z Own Label", item_group="Private Label", **same)
		make_test_item("_Test Sub Disabled", disabled=1, **same)
		make_test_item("_Test Sub Other Strength", nir_salt=SALT, nir_strength="650 mg")
		make_test_item("_Test Sub No Salt")

	def test_same_salt_and_strength_private_label_first(self):
		substitutes = get_substitutes("_Test Sub Brand A")
		self.assertEqual([s.item_code for s in substitutes], ["_Test Sub Own Label", "_Test Sub Brand B"])
		self.assertEqual(substitutes[0].is_private_label, 1)

	def test_item_without_salt_has_no_substitutes(self):
		self.assertEqual(get_substitutes("_Test Sub No Salt"), [])
