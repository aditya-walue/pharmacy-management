# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""A customer's purchases (by customer or mobile): bill, store, item, batch, quantity and prescription."""

import frappe
from frappe import _

from pharmacy.overrides.customer import normalise_mobile


def execute(filters=None):
	filters = frappe._dict(filters or {})
	customer = filters.customer
	if not customer and filters.mobile:
		customer = frappe.db.get_value("Customer", {"nir_mobile": normalise_mobile(filters.mobile)})
	if not customer:
		return columns(), []

	rows = []
	for doctype, child in (("Sales Invoice", "Sales Invoice Item"), ("POS Invoice", "POS Invoice Item")):
		consolidated = "and ifnull(p.is_consolidated, 0) = 0" if doctype == "Sales Invoice" else "and p.status != 'Consolidated'"
		rows += frappe.db.sql(
			f"""select p.posting_date, '{doctype}' as voucher_type, p.name as voucher_no, p.is_return, i.warehouse,
				i.item_code, i.item_name, i.batch_no, i.qty, i.uom, i.rate, i.amount, p.nir_customer_prescription as prescription,
				p.nir_doctor_name as doctor_name
			from `tab{child}` i join `tab{doctype}` p on p.name = i.parent
			where p.docstatus = 1 and p.customer = %(customer)s {consolidated}
				and p.posting_date between %(from_date)s and %(to_date)s""",
			{"customer": customer, "from_date": filters.from_date or "2000-01-01", "to_date": filters.to_date or "2999-12-31"},
			as_dict=True,
		)
	return columns(), sorted(rows, key=lambda r: (r.posting_date, r.voucher_no), reverse=True)


def columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "voucher_no", "label": _("Bill"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
		{"fieldname": "voucher_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "is_return", "label": _("Return"), "fieldtype": "Check", "width": 60},
		{"fieldname": "warehouse", "label": _("Store"), "fieldtype": "Link", "options": "Warehouse", "width": 140},
		{"fieldname": "item_name", "label": _("Item"), "fieldtype": "Data", "width": 180},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 140},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 60},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 60},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 90},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "prescription", "label": _("Prescription"), "fieldtype": "Link", "options": "Customer Prescription", "width": 120},
		{"fieldname": "doctor_name", "label": _("Doctor"), "fieldtype": "Data", "width": 120},
	]
