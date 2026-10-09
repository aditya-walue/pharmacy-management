# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Schedule H1 register, filled from store bills: date, patient, prescriber, drug, batch and quantity."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"register_type": "Schedule H1"}
	if filters.from_date and filters.to_date:
		conditions["posting_date"] = ("between", (filters.from_date, filters.to_date))
	for key in ("company", "warehouse", "item_code"):
		if filters.get(key):
			conditions[key] = filters.get(key)
	rows = frappe.get_all(
		"Controlled Drug Register",
		filters=conditions,
		fields=["posting_date", "voucher_type", "voucher_no", "transaction_type", "patient_name", "patient_address",
			"doctor_name", "doctor_reg_no", "item_code", "item_name", "batch_no", "expiry_date", "qty_out", "qty_in",
			"stock_uom", "warehouse", "prescription"],
		order_by="posting_date asc, creation asc",
	)
	for r in rows:
		r.qty = (r.qty_out or 0) - (r.qty_in or 0)
	return columns(), rows


def columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "voucher_no", "label": _("Bill"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
		{"fieldname": "voucher_type", "label": _("Bill Type"), "fieldtype": "Data", "width": 1, "hidden": 1},
		{"fieldname": "transaction_type", "label": _("Entry"), "fieldtype": "Data", "width": 90},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 150},
		{"fieldname": "patient_address", "label": _("Patient Address"), "fieldtype": "Data", "width": 180},
		{"fieldname": "doctor_name", "label": _("Prescriber"), "fieldtype": "Data", "width": 140},
		{"fieldname": "doctor_reg_no", "label": _("Reg. No"), "fieldtype": "Data", "width": 110},
		{"fieldname": "item_name", "label": _("Drug"), "fieldtype": "Data", "width": 170},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 140},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 90},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 70},
		{"fieldname": "stock_uom", "label": _("UOM"), "fieldtype": "Data", "width": 60},
		{"fieldname": "warehouse", "label": _("Store"), "fieldtype": "Link", "options": "Warehouse", "width": 140},
		{"fieldname": "prescription", "label": _("Prescription"), "fieldtype": "Data", "width": 150},
	]
