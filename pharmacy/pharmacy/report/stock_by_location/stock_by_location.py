# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Stock by site, zone, bin, item and batch with expiry, MRP, ageing and valuation (WH-01)."""

import frappe
from frappe import _
from frappe.utils import flt

from pharmacy.overrides.inventory import age_bucket, enrich, get_batch_stock
from pharmacy.overrides.stock_hold import find_hold, get_active_holds
from pharmacy.overrides.warehouse_layout import get_layout

BUCKETS = ("0-30", "31-90", "91-180", "180+")
GROUP_KEYS = {
	"Batch": ("site", "zone", "warehouse", "item_code", "batch_no"),
	"Bin": ("site", "zone", "warehouse"),
	"Zone": ("site", "zone"),
	"Site": ("site",),
	"Item": ("item_code",),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	layout = get_layout(filters.company)
	warehouses = None
	if filters.warehouse:
		lft, rgt = frappe.db.get_value("Warehouse", filters.warehouse, ["lft", "rgt"])
		warehouses = [w.name for w in layout.values() if w.lft >= lft and w.rgt <= rgt]

	rows = enrich(get_batch_stock(company=filters.company, warehouses=warehouses, item_codes=[filters.item_code] if filters.item_code else None))
	holds = get_active_holds({r.item_code for r in rows})
	data = []
	for r in rows:
		w = layout.get(r.warehouse, frappe._dict())
		r.site, r.zone = w.site, w.zone_type
		if filters.zone_type and r.zone != filters.zone_type:
			continue
		if filters.regulatory_category and r.regulatory_category != filters.regulatory_category:
			continue
		if filters.expiring_within and (r.days_to_expiry is None or r.days_to_expiry > flt(filters.expiring_within)):
			continue
		r.age_bucket = age_bucket(r.age_days)
		r.held = 1 if find_hold(holds, r.item_code, [r.batch_no] if r.batch_no else [], r.warehouse) else 0
		data.append(r)

	group_by = filters.group_by or "Batch"
	if group_by == "Batch":
		return detail_columns(), sorted(data, key=lambda r: (r.site or "", r.zone or "", r.warehouse, r.item_code, r.batch_no or ""))
	return summary_columns(group_by), summarise(data, GROUP_KEYS[group_by])


def summarise(data, keys):
	"""Qty and value per group, with value split by age bucket."""
	groups = {}
	for r in data:
		g = groups.setdefault(tuple(r.get(k) for k in keys), frappe._dict({k: r.get(k) for k in keys}, qty=0, value=0))
		if "item_code" in keys:
			g.item_name = r.item_name
		g.qty += flt(r.qty)
		g.value += flt(r.value)
		bucket = f"value_{(r.age_bucket or 'unknown').replace('-', '_').replace('+', '_plus')}"
		g[bucket] = flt(g.get(bucket)) + flt(r.value)
	return sorted(groups.values(), key=lambda g: tuple(str(g.get(k) or "") for k in keys))


def detail_columns():
	return [
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Warehouse", "width": 140},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Data", "width": 110},
		{"fieldname": "warehouse", "label": _("Bin"), "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "regulatory_category", "label": _("Category"), "fieldtype": "Data", "width": 100},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 150},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 95},
		{"fieldname": "days_to_expiry", "label": _("Days to Expiry"), "fieldtype": "Int", "width": 100},
		{"fieldname": "mrp", "label": _("MRP"), "fieldtype": "Currency", "width": 90},
		{"fieldname": "mrp_uom", "label": _("MRP per"), "fieldtype": "Data", "width": 70},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "stock_uom", "label": _("UOM"), "fieldtype": "Data", "width": 60},
		{"fieldname": "valuation_rate", "label": _("Valuation Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "age_days", "label": _("Age (Days)"), "fieldtype": "Int", "width": 85},
		{"fieldname": "age_bucket", "label": _("Age Bucket"), "fieldtype": "Data", "width": 85},
		{"fieldname": "held", "label": _("On Hold"), "fieldtype": "Check", "width": 70},
	]


def summary_columns(group_by):
	labels = {"site": (_("Site"), "Warehouse"), "zone": (_("Zone"), None), "warehouse": (_("Bin"), "Warehouse"), "item_code": (_("Item"), "Item")}
	columns = []
	for key in GROUP_KEYS[group_by]:
		label, options = labels[key]
		columns.append({"fieldname": key, "label": label, "fieldtype": "Link" if options else "Data", "options": options, "width": 160})
	if group_by == "Item":
		columns.append({"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180})
	columns += [
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 130},
	] + [
		{"fieldname": f"value_{b.replace('-', '_').replace('+', '_plus')}", "label": _("Value {0} days").format(b), "fieldtype": "Currency", "width": 130}
		for b in BUCKETS
	]
	return columns
