"""Customers are found by mobile number, so one number belongs to one customer."""

import re

import frappe
from frappe import _


def normalise_mobile(value):
	"""Keep the last 10 digits, so +91 98200 12345 and 9820012345 are the same number."""
	digits = re.sub(r"\D", "", value or "")
	return digits[-10:] if len(digits) >= 10 else digits


def validate_mobile(doc, method=None):
	if not doc.get("nir_mobile"):
		return
	doc.nir_mobile = normalise_mobile(doc.nir_mobile)
	if len(doc.nir_mobile) != 10:
		frappe.throw(_("Enter a 10-digit mobile number"))
	other = frappe.db.get_value("Customer", {"nir_mobile": doc.nir_mobile, "name": ("!=", doc.name)})
	if other:
		frappe.throw(_("Mobile {0} already belongs to customer {1}").format(doc.nir_mobile, other), frappe.DuplicateEntryError)


@frappe.whitelist()
def find_by_mobile(mobile: str):
	frappe.has_permission("Customer", "read", throw=True)
	return frappe.db.get_value("Customer", {"nir_mobile": normalise_mobile(mobile)}, ["name", "customer_name"], as_dict=True)
