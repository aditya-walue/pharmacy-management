"""Prescriptions on retail sale of Rx items, saved per customer, and the registers filled from the bill.

Schedule H, H1, X and NDPS items need the prescription (photo or scan), doctor name and registration number;
H1, X and NDPS also need the patient, because their registers record who the drug was sold to.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from pharmacy.overrides.party_licence import has_licences

REGISTER_CATEGORIES = ("Schedule H1", "Schedule X", "NDPS")


def is_retail_bill(doc):
	"""Store sales to consumers: not returns, consolidations, transfers to stores or B2B buyers."""
	if doc.get("is_return") or doc.get("is_consolidated") or doc.get("is_internal_customer"):
		return False
	if doc.get("nir_pick_wave") or doc.get("nir_store_transfer"):
		return False
	if doc.doctype == "Sales Invoice" and not (doc.get("update_stock") or doc.get("is_pos")):
		return False
	return not (doc.get("customer") and has_licences("Customer", doc.customer))


def fill_from_saved_prescription(doc, method=None):
	"""validate: a chosen saved prescription fills the bill; a named customer is the default patient."""
	if doc.get("nir_customer_prescription"):
		rx = frappe.db.get_value(
			"Customer Prescription", doc.nir_customer_prescription,
			["customer", "prescription_file", "doctor_name", "doctor_reg_no", "patient_name", "patient_address", "valid_upto"],
			as_dict=True,
		)
		if rx.customer != doc.customer:
			frappe.throw(_("Prescription {0} belongs to another customer").format(doc.nir_customer_prescription))
		if rx.valid_upto and getdate(rx.valid_upto) < getdate(doc.posting_date):
			frappe.throw(_("Prescription {0} expired on {1}; capture a new one").format(
				doc.nir_customer_prescription, frappe.format(rx.valid_upto, "Date")))
		doc.nir_prescription = doc.nir_prescription or rx.prescription_file
		doc.nir_doctor_name = doc.nir_doctor_name or rx.doctor_name
		doc.nir_doctor_reg_no = doc.nir_doctor_reg_no or rx.doctor_reg_no
		doc.nir_patient_name = doc.nir_patient_name or rx.patient_name
		doc.nir_patient_address = doc.nir_patient_address or rx.patient_address

	if not doc.get("nir_patient_name") and doc.get("customer") and not is_walk_in(doc):
		doc.nir_patient_name = doc.customer_name or doc.customer


def is_walk_in(doc):
	default_customer = frappe.db.get_value("POS Profile", doc.pos_profile, "customer") if doc.get("pos_profile") else None
	return doc.customer == default_customer


def get_categories(doc):
	item_codes = list({row.item_code for row in doc.get("items") or [] if row.get("item_code")})
	if not item_codes:
		return {}
	return dict(frappe.get_all("Item", filters={"name": ("in", item_codes)},
		fields=["name", "nir_regulatory_category"], as_list=True))


def validate_prescription(doc, method=None):
	"""before_submit: no Rx sale without prescription, doctor and (for register drugs) patient."""
	if not is_retail_bill(doc):
		return

	rx_items = frappe.get_all(
		"Item",
		filters={"name": ("in", list({r.item_code for r in doc.items if r.item_code})), "nir_rx_required": 1},
		pluck="name",
	)
	if not rx_items:
		return

	if not (doc.get("nir_prescription") and doc.get("nir_doctor_name") and doc.get("nir_doctor_reg_no")):
		frappe.throw(
			_("Prescription, Doctor Name, and Doctor Registration No are required for Rx items: {0}").format(
				", ".join(sorted(rx_items))
			),
			title=_("Prescription required"),
		)

	register_items = [code for code, cat in get_categories(doc).items() if cat in REGISTER_CATEGORIES]
	if register_items and not doc.get("nir_patient_name"):
		frappe.throw(
			_("Patient Name is required for the register: {0}").format(", ".join(sorted(register_items))),
			title=_("Patient required"),
		)


def save_prescription(doc, method=None):
	"""on_submit: a new prescription captured for a named customer is kept on their record."""
	if not is_retail_bill(doc) or doc.get("nir_customer_prescription") or not doc.get("nir_prescription"):
		return
	if is_walk_in(doc) or not (doc.get("nir_doctor_name") and doc.get("nir_doctor_reg_no")):
		return
	rx = frappe.get_doc({
		"doctype": "Customer Prescription",
		"customer": doc.customer,
		"patient_name": doc.nir_patient_name or doc.customer_name,
		"patient_address": doc.get("nir_patient_address"),
		"prescription_date": doc.posting_date,
		"doctor_name": doc.nir_doctor_name,
		"doctor_reg_no": doc.nir_doctor_reg_no,
		"prescription_file": doc.nir_prescription,
		"notes": ", ".join(sorted({r.item_name or r.item_code for r in doc.items})),
		"source_invoice" if doc.doctype == "Sales Invoice" else "source_pos_invoice": doc.name,
	}).insert(ignore_permissions=True)
	doc.db_set("nir_customer_prescription", rx.name)
