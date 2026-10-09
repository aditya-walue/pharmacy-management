# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Totes, crates and ice boxes by store: issued and returned in the period, held now, overdue, missing."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime

from pharmacy.overrides.tote_tracking import DEFAULT_RETURN_DAYS


def execute(filters=None):
	filters = frappe._dict(filters or {})
	days = cint(frappe.db.get_single_value("Stock Settings", "nir_tote_return_days")) or DEFAULT_RETURN_DAYS
	overdue_before = add_days(now_datetime(), -days)

	rows = {}

	def row(store, tote_type):
		return rows.setdefault((store, tote_type), frappe._dict(store=store, tote_type=tote_type, issued=0, returned=0,
			damaged=0, held=0, overdue=0, missing=0))

	conditions, values = ["store_warehouse is not null"], {}
	if filters.from_date:
		conditions.append("date(posted_on) >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append("date(posted_on) <= %(to_date)s")
		values["to_date"] = filters.to_date
	for m in frappe.db.sql(
		f"""select store_warehouse, tote_type, event, condition, count(*) as n from `tabTote Movement`
		where {" and ".join(conditions)} group by store_warehouse, tote_type, event, condition""",
		values,
		as_dict=True,
	):
		r = row(m.store_warehouse, m.tote_type)
		if m.event == "Issued":
			r.issued += m.n
		elif m.event == "Returned":
			r.returned += m.n
			if m.condition == "Damaged":
				r.damaged += m.n

	for t in frappe.get_all("Tote", filters={"status": ("in", ("At Store", "Missing"))}, fields=["holder_store", "tote_type", "status", "issued_on"]):
		r = row(t.holder_store, t.tote_type)
		if t.status == "Missing":
			r.missing += 1
		else:
			r.held += 1
			if t.issued_on and t.issued_on < overdue_before:
				r.overdue += 1

	data = [r for r in rows.values() if not filters.store or r.store == filters.store]
	return columns(days), sorted(data, key=lambda r: (r.store or "", r.tote_type or ""))


def columns(days):
	return [
		{"fieldname": "store", "label": _("Store"), "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"fieldname": "tote_type", "label": _("Type"), "fieldtype": "Data", "width": 150},
		{"fieldname": "issued", "label": _("Issued"), "fieldtype": "Int", "width": 80},
		{"fieldname": "returned", "label": _("Returned"), "fieldtype": "Int", "width": 90},
		{"fieldname": "damaged", "label": _("Returned Damaged"), "fieldtype": "Int", "width": 130},
		{"fieldname": "held", "label": _("Held Now"), "fieldtype": "Int", "width": 90},
		{"fieldname": "overdue", "label": _("Overdue (> {0} days)").format(days), "fieldtype": "Int", "width": 140},
		{"fieldname": "missing", "label": _("Missing"), "fieldtype": "Int", "width": 90},
	]
