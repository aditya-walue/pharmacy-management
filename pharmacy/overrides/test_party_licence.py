# Copyright (c) 2026, Aditya and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.overrides.party_licence import validate_party_licence
from pharmacy.tests.utils import make_test_item

SCHEDULE_H = "_Test Licence Schedule H Item"
SCHEDULE_X = "_Test Licence Schedule X Item"
COSMETIC = "_Test Licence Cosmetic Item"
SUPPLIER = "_Test Licence Supplier"
CUSTOMER = "_Test Licence Retail Customer"
CHEMIST = "_Test Licence Chemist"


def make_licence(party_type, party, form, valid_upto=None):
	frappe.get_doc(
		{
			"doctype": "Drug Licence",
			"party_type": party_type,
			"party": party,
			"licence_form": form,
			"licence_no": f"{party}-{form}",
			"valid_from": add_days(today(), -365),
			"valid_upto": valid_upto or add_days(today(), 365),
		}
	).insert()


def make_warehouse(name, parent, is_group=0):
	company = frappe.db.get_value("Company", {})
	abbr = frappe.db.get_value("Company", company, "abbr")
	full_name = f"{name} - {abbr}"
	if not frappe.db.exists("Warehouse", full_name):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": name,
				"company": company,
				"parent_warehouse": parent,
				"is_group": is_group,
			}
		).insert()
	return full_name


def purchase(item, supplier=SUPPLIER, warehouse=None, **kwargs):
	return frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"transaction_date": today(),
			"items": [{"item_code": item, "warehouse": warehouse or TestPartyLicence.dc_bin}],
			**kwargs,
		}
	)


def sale(item, customer=CUSTOMER, warehouse=None, **kwargs):
	return frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"posting_date": today(),
			"items": [{"item_code": item, "warehouse": warehouse or TestPartyLicence.store}],
			**kwargs,
		}
	)


def transfer(item, source, target):
	return frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"purpose": "Material Transfer",
			"posting_date": today(),
			"items": [{"item_code": item, "s_warehouse": source, "t_warehouse": target}],
		}
	)


class TestPartyLicence(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_test_item(SCHEDULE_H, nir_regulatory_category="Schedule H")
		make_test_item(SCHEDULE_X, nir_regulatory_category="Schedule X")
		make_test_item(COSMETIC, nir_regulatory_category="Cosmetic")

		for supplier in (SUPPLIER, "_Test Licence Retail-only Supplier", "_Test Licence Unlicensed Supplier"):
			if not frappe.db.exists("Supplier", supplier):
				frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier, "supplier_type": "Company"}).insert()
		for customer in (CUSTOMER, CHEMIST):
			if not frappe.db.exists("Customer", customer):
				frappe.get_doc({"doctype": "Customer", "customer_name": customer}).insert()

		root = frappe.db.get_value("Warehouse", {"is_group": 1, "parent_warehouse": ("is", "not set")})
		dc = make_warehouse("_Test Licence DC", root, is_group=1)
		cls.dc, cls.dc_bin = dc, make_warehouse("_Test Licence DC Bin", dc)
		cls.store = make_warehouse("_Test Licence Store", root)
		cls.unlicensed_store = make_warehouse("_Test Licence Unlicensed Store", root)
		frappe.db.delete("Drug Licence", {"party": cls.unlicensed_store})

		make_licence("Supplier", SUPPLIER, "20B")
		make_licence("Supplier", "_Test Licence Retail-only Supplier", "20")
		make_licence("Warehouse", dc, "20B")
		make_licence("Warehouse", cls.store, "20")
		make_licence("Customer", CHEMIST, "20")

	def assertBlocked(self, doc):
		with self.assertRaises(frappe.ValidationError):
			validate_party_licence(doc)

	def test_purchase_from_wholesaler_into_dc_bin_allowed(self):
		# the bin has no licence of its own; its DC's 20B covers it
		validate_party_licence(purchase(SCHEDULE_H))

	def test_purchase_from_retail_only_supplier_blocked(self):
		self.assertBlocked(purchase(SCHEDULE_H, supplier="_Test Licence Retail-only Supplier"))

	def test_schedule_x_needs_form_20g(self):
		self.assertBlocked(purchase(SCHEDULE_X))

	def expire_supplier_licence(self):
		licence = frappe.db.get_value("Drug Licence", {"party": SUPPLIER}, ["name", "valid_upto"], as_dict=True)
		frappe.db.set_value("Drug Licence", licence.name, "valid_upto", add_days(today(), -1))
		self.addCleanup(frappe.db.set_value, "Drug Licence", licence.name, "valid_upto", licence.valid_upto)

	def test_expired_supplier_licence_blocked(self):
		self.expire_supplier_licence()
		self.assertBlocked(purchase(SCHEDULE_H))

	def test_back_dated_purchase_uses_licence_valid_then(self):
		self.expire_supplier_licence()
		validate_party_licence(purchase(SCHEDULE_H, transaction_date=add_days(today(), -30)))

	def test_cosmetic_needs_no_licence(self):
		validate_party_licence(purchase(COSMETIC, supplier="_Test Licence Unlicensed Supplier"))

	def test_retail_sale_from_licensed_store_allowed(self):
		validate_party_licence(sale(SCHEDULE_H))

	def test_retail_sale_from_wholesale_dc_blocked(self):
		# a 20B wholesale licence does not permit selling to consumers
		self.assertBlocked(sale(SCHEDULE_H, warehouse=self.dc_bin))

	def test_sale_from_unlicensed_store_blocked(self):
		self.assertBlocked(sale(SCHEDULE_H, warehouse=self.unlicensed_store))

	def test_b2b_sale_from_dc_to_licensed_chemist_allowed(self):
		validate_party_licence(sale(SCHEDULE_H, customer=CHEMIST, warehouse=self.dc_bin))

	def test_sales_return_not_checked(self):
		validate_party_licence(sale(SCHEDULE_H, warehouse=self.unlicensed_store, is_return=1))

	def test_transfer_within_dc_not_checked(self):
		validate_party_licence(transfer(SCHEDULE_H, self.dc_bin, self.dc))

	def test_transfer_to_unlicensed_store_blocked(self):
		self.assertBlocked(transfer(SCHEDULE_H, self.dc_bin, self.unlicensed_store))

	def test_transfer_to_licensed_store_allowed(self):
		validate_party_licence(transfer(SCHEDULE_H, self.dc_bin, self.store))
