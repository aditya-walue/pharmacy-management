# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Live store stock (ST-05): on hand, in transit, pending indents, sales rate and cover per store and item."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, today

from pharmacy.overrides.store_transfer import get_shipments


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = int(filters.sales_days or 30)
	stores = [filters.store] if filters.store else frappe.get_all("Pharmacy Store", filters={"disabled": 0}, pluck="warehouse")
	stores = [s for s in stores if s]
	if not stores:
		return columns(), []

	on_hand = frappe.db.sql(
		"""select warehouse, item_code, actual_qty, stock_value from `tabBin` where warehouse in %s and actual_qty != 0""",
		[tuple(stores)], as_dict=True,
	)
	sales = {(r.warehouse, r.item_code): -flt(r.qty) for r in frappe.db.sql(
		"""select warehouse, item_code, sum(actual_qty) as qty from `tabStock Ledger Entry`
		where warehouse in %s and is_cancelled = 0 and actual_qty < 0 and posting_date >= %s
			and voucher_type in ('Sales Invoice', 'POS Invoice', 'Delivery Note')
		group by warehouse, item_code""", (tuple(stores), add_days(today(), -period)), as_dict=True)}
	pending = {(r.warehouse, r.item_code): flt(r.qty) for r in frappe.db.sql(
		"""select mri.warehouse, mri.item_code, sum(mri.stock_qty - mri.ordered_qty - ifnull(mri.nir_cancelled_qty, 0)) as qty
		from `tabMaterial Request Item` mri join `tabMaterial Request` mr on mr.name = mri.parent
		where mr.docstatus = 1 and mr.material_request_type = 'Material Transfer' and mr.status not in ('Stopped', 'Cancelled', 'Transferred')
			and mri.warehouse in %s group by mri.warehouse, mri.item_code""", [tuple(stores)], as_dict=True)}

	in_transit = {}
	for s in get_shipments(filters.store):
		if s.store not in stores:
			continue
		child, qty = ("Stock Entry Detail", "transfer_qty") if s.doctype == "Stock Entry" else ("Sales Invoice Item", "stock_qty")
		for r in frappe.get_all(child, filters={"parent": s.name}, fields=["item_code", qty]):
			key = (s.store, r.item_code)
			in_transit[key] = in_transit.get(key, 0) + flt(r[qty])

	rows = {}
	for r in on_hand:
		rows[(r.warehouse, r.item_code)] = {"qty": flt(r.actual_qty), "value": flt(r.stock_value)}
	for key in set(in_transit) | set(pending):
		rows.setdefault(key, {"qty": 0, "value": 0})

	data = []
	for (store, item), r in rows.items():
		sold = sales.get((store, item), 0)
		daily = sold / period
		data.append({
			"store": store, "item_code": item, "item_name": frappe.get_cached_value("Item", item, "item_name"),
			"qty": r["qty"], "value": r["value"], "in_transit": in_transit.get((store, item), 0),
			"pending_indent": max(pending.get((store, item), 0), 0), "sold": sold, "daily_sales": daily,
			"days_of_cover": r["qty"] / daily if daily else None,
		})
	if filters.item_code:
		data = [d for d in data if d["item_code"] == filters.item_code]
	return columns(), sorted(data, key=lambda d: (d["store"], d["item_code"]))


def columns():
	return [
		{"fieldname": "store", "label": _("Store"), "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "qty", "label": _("On Hand"), "fieldtype": "Float", "width": 90},
		{"fieldname": "value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "in_transit", "label": _("In Transit"), "fieldtype": "Float", "width": 90},
		{"fieldname": "pending_indent", "label": _("Pending Indent"), "fieldtype": "Float", "width": 110},
		{"fieldname": "sold", "label": _("Sold in Period"), "fieldtype": "Float", "width": 110},
		{"fieldname": "daily_sales", "label": _("Avg Daily Sales"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "days_of_cover", "label": _("Days of Cover"), "fieldtype": "Float", "precision": 0, "width": 110},
	]
