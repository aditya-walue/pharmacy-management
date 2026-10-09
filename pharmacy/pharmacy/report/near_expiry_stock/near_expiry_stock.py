# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Batches in stock expiring within N days, bucketed for 30/60/90/180-day action (WH-06)."""

import frappe
from frappe import _
from frappe.utils import flt

from pharmacy.overrides.inventory import enrich, get_batch_stock
from pharmacy.overrides.warehouse_layout import get_layout


def execute(filters=None):
	filters = frappe._dict(filters or {})
	within = flt(filters.within_days) or 180
	layout = get_layout(filters.company)
	warehouses = None
	if filters.warehouse:
		lft, rgt = frappe.db.get_value("Warehouse", filters.warehouse, ["lft", "rgt"])
		warehouses = [w.name for w in layout.values() if w.lft >= lft and w.rgt <= rgt]

	data = []
	for r in enrich(get_batch_stock(company=filters.company, warehouses=warehouses)):
		if flt(r.qty) <= 0 or r.days_to_expiry is None or r.days_to_expiry > within:
			continue
		w = layout.get(r.warehouse, frappe._dict())
		r.site, r.zone = w.site, w.zone_type
		r.expiry_bucket = bucket(r.days_to_expiry)
		data.append(r)
	data.sort(key=lambda r: (r.days_to_expiry, r.item_code))
	return columns(), data


def bucket(days):
	if days < 0:
		return _("Expired")
	for limit in (30, 60, 90, 180):
		if days <= limit:
			return _("Within {0} days").format(limit)
	return _("Beyond 180 days")


def columns():
	return [
		{"fieldname": "expiry_bucket", "label": _("Bucket"), "fieldtype": "Data", "width": 120},
		{"fieldname": "days_to_expiry", "label": _("Days Left"), "fieldtype": "Int", "width": 80},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 95},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 150},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Warehouse", "width": 130},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Data", "width": 100},
		{"fieldname": "warehouse", "label": _("Bin"), "fieldtype": "Link", "options": "Warehouse", "width": 140},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "mrp", "label": _("MRP"), "fieldtype": "Currency", "width": 90},
		{"fieldname": "value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 120},
	]
