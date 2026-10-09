# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Slow-moving and non-moving stock per item and warehouse (WH-06).

Movement is any outward stock ledger entry other than a reconciliation, so bin moves count too.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period = int(filters.period_days or 90)
	non_moving_days = int(filters.non_moving_days or 180)
	slow_cover_days = int(filters.slow_cover_days or 90)
	since = add_days(today(), -period)

	conditions, values = ["bin.actual_qty > 0", "wh.company = %(company)s"], {"company": filters.company, "since": since}
	if filters.warehouse:
		lft, rgt = frappe.db.get_value("Warehouse", filters.warehouse, ["lft", "rgt"])
		conditions.append("wh.lft >= %(lft)s and wh.rgt <= %(rgt)s")
		values.update(lft=lft, rgt=rgt)
	if filters.item_group:
		conditions.append("item.item_group = %(item_group)s")
		values["item_group"] = filters.item_group

	rows = frappe.db.sql(
		f"""select bin.warehouse, bin.item_code, item.item_name, item.item_group, item.nir_abc_class as abc_class,
			bin.actual_qty as qty, bin.stock_value as value,
			(select max(sle.posting_date) from `tabStock Ledger Entry` sle
				where sle.item_code = bin.item_code and sle.warehouse = bin.warehouse and sle.is_cancelled = 0
				and sle.actual_qty < 0 and sle.voucher_type != 'Stock Reconciliation') as last_outward,
			(select ifnull(-sum(sle.actual_qty), 0) from `tabStock Ledger Entry` sle
				where sle.item_code = bin.item_code and sle.warehouse = bin.warehouse and sle.is_cancelled = 0
				and sle.actual_qty < 0 and sle.voucher_type != 'Stock Reconciliation'
				and sle.posting_date >= %(since)s) as outward_qty
		from `tabBin` bin
		join `tabItem` item on item.name = bin.item_code
		join `tabWarehouse` wh on wh.name = bin.warehouse
		where {" and ".join(conditions)}""",
		values,
		as_dict=True,
	)

	data = []
	for r in rows:
		r.days_since_outward = date_diff(today(), r.last_outward) if r.last_outward else None
		daily = flt(r.outward_qty) / period
		r.days_of_cover = flt(r.qty) / daily if daily else None
		if r.days_since_outward is None or r.days_since_outward > non_moving_days:
			r.movement = _("Non-Moving")
		elif r.days_of_cover is None or r.days_of_cover > slow_cover_days:
			r.movement = _("Slow-Moving")
		else:
			r.movement = _("Moving")
		if filters.show != "All" and r.movement == _("Moving"):
			continue
		data.append(r)
	data.sort(key=lambda r: (r.movement != _("Non-Moving"), -flt(r.value)))
	return columns(), data


def columns():
	return [
		{"fieldname": "movement", "label": _("Movement"), "fieldtype": "Data", "width": 110},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"fieldname": "abc_class", "label": _("ABC"), "fieldtype": "Data", "width": 50},
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "last_outward", "label": _("Last Outward"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_since_outward", "label": _("Days Since Outward"), "fieldtype": "Int", "width": 130},
		{"fieldname": "outward_qty", "label": _("Outward in Period"), "fieldtype": "Float", "width": 120},
		{"fieldname": "days_of_cover", "label": _("Days of Cover"), "fieldtype": "Float", "precision": 0, "width": 110},
	]
