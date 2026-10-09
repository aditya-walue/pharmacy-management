# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.overrides.prescription import validate_prescription
from pharmacy.tests.utils import make_test_item

RX_ITEM = "_Test Prescription Rx Item"
NON_RX_ITEM = "_Test Prescription Non-Rx Item"
RETAIL_CUST = "_Test Prescription Retail Customer"
B2B_CUST = "_Test Prescription B2B Customer"


def make_licence(party_type, party, form):
	doc = frappe.get_doc(
		{
			"doctype": "Drug Licence",
			"party_type": party_type,
			"party": party,
			"licence_form": form,
			"licence_no": f"{party}-{form}",
			"valid_from": add_days(today(), -365),
			"valid_upto": add_days(today(), 365),
		}
	).insert()
	return doc


class TestPrescriptionRules(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_test_item(RX_ITEM, nir_rx_required=1, nir_regulatory_category="Schedule H")
		make_test_item(NON_RX_ITEM, nir_rx_required=0, nir_regulatory_category="OTC")

		for cust in (RETAIL_CUST, B2B_CUST):
			if not frappe.db.exists("Customer", cust):
				frappe.get_doc({"doctype": "Customer", "customer_name": cust}).insert()

		cls.licence = make_licence("Customer", B2B_CUST, "20")

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.delete("Drug Licence", {"name": cls.licence.name})

	def assertBlocked(self, doc):
		with self.assertRaises(frappe.ValidationError):
			validate_prescription(doc)

	def test_non_rx_item_without_prescription_allowed(self):
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"items": [{"item_code": NON_RX_ITEM}],
		})
		validate_prescription(si)

	def test_rx_item_without_prescription_blocked(self):
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"update_stock": 1,
			"items": [{"item_code": RX_ITEM}],
		})
		self.assertBlocked(si)

	def test_rx_item_with_partial_fields_blocked(self):
		# Missing doctor name and reg no
		si_partial1 = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"update_stock": 1,
			"items": [{"item_code": RX_ITEM}],
			"nir_prescription": "/files/rx.pdf",
		})
		self.assertBlocked(si_partial1)

		# Missing doctor reg no
		si_partial2 = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"update_stock": 1,
			"items": [{"item_code": RX_ITEM}],
			"nir_prescription": "/files/rx.pdf",
			"nir_doctor_name": "Dr. Smith",
		})
		self.assertBlocked(si_partial2)

	def test_rx_item_with_all_fields_allowed(self):
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"items": [{"item_code": RX_ITEM}],
			"nir_prescription": "/files/rx.pdf",
			"nir_doctor_name": "Dr. Smith",
			"nir_doctor_reg_no": "MCI-12345",
		})
		validate_prescription(si)

	def test_pos_invoice_with_rx_item(self):
		pos_fail = frappe.get_doc({
			"doctype": "POS Invoice",
			"customer": RETAIL_CUST,
			"items": [{"item_code": RX_ITEM}],
		})
		self.assertBlocked(pos_fail)

		pos_pass = frappe.get_doc({
			"doctype": "POS Invoice",
			"customer": RETAIL_CUST,
			"items": [{"item_code": RX_ITEM}],
			"nir_prescription": "/files/rx.pdf",
			"nir_doctor_name": "Dr. Smith",
			"nir_doctor_reg_no": "MCI-12345",
		})
		validate_prescription(pos_pass)

	def test_licensed_b2b_customer_exempt(self):
		# Customer has Drug Licence -> prescription fields not required even for Rx items
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": B2B_CUST,
			"items": [{"item_code": RX_ITEM}],
		})
		validate_prescription(si)

	def test_return_exempt(self):
		si_return = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"is_return": 1,
			"items": [{"item_code": RX_ITEM}],
		})
		validate_prescription(si_return)

	def test_consolidated_exempt(self):
		si_cons = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": RETAIL_CUST,
			"is_consolidated": 1,
			"items": [{"item_code": RX_ITEM}],
		})
		validate_prescription(si_cons)
