# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from pharmacy.overrides.po_fulfilment import get_supplier_performance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	performance = get_supplier_performance(
		filters.from_date, filters.to_date, company=filters.company, supplier=filters.supplier
	)
	promised = dict(
		frappe.get_all(
			"Supplier",
			filters={"name": ("in", list(performance))},
			fields=["name", "nir_lead_time_days"],
			as_list=True,
		)
	)
	data = [
		{"supplier": supplier, "promised_lead_time": promised.get(supplier), **p}
		for supplier, p in sorted(performance.items())
	]
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 200},
		{"fieldname": "purchase_orders", "label": _("POs"), "fieldtype": "Int", "width": 70},
		{"fieldname": "completed_orders", "label": _("Supply Complete"), "fieldtype": "Int", "width": 120},
		{"fieldname": "qty_fill_rate", "label": _("Qty Fill Rate"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "line_fill_rate", "label": _("Line Fill Rate"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "avg_lead_time", "label": _("Avg Lead Time (Days)"), "fieldtype": "Float", "precision": 1, "width": 150},
		{"fieldname": "promised_lead_time", "label": _("Promised Lead Time"), "fieldtype": "Int", "width": 140},
		{"fieldname": "on_time_pct", "label": _("On Time"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "short_closed", "label": _("Short Closed"), "fieldtype": "Int", "width": 110},
		{"fieldname": "pending_qty", "label": _("Pending Qty"), "fieldtype": "Float", "width": 110},
	]
