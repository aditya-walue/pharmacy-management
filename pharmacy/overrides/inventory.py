"""Stock position by warehouse, item and batch (WH-01), shared by reports, counts, top-ups and alerts."""

import frappe
from frappe.utils import date_diff, flt, getdate, today


def get_batch_stock(company=None, warehouses=None, item_codes=None, batch_nos=None):
	"""Rows of warehouse, item_code, batch_no, qty, value, first_receipt for stock on hand.

	Batched items come from Serial and Batch Entries (qty and value per batch); items without
	batches come from Bin.
	"""
	conditions, values = ["sbe.docstatus = 1", "sbe.is_cancelled = 0", "ifnull(sbe.batch_no, '') != ''"], {}
	bin_conditions = ["bin.actual_qty != 0", "item.has_batch_no = 0"]
	if company:
		conditions.append("wh.company = %(company)s")
		bin_conditions.append("wh.company = %(company)s")
		values["company"] = company
	if warehouses:
		conditions.append("sbe.warehouse in %(warehouses)s")
		bin_conditions.append("bin.warehouse in %(warehouses)s")
		values["warehouses"] = tuple(warehouses)
	if item_codes:
		conditions.append("sbe.item_code in %(items)s")
		bin_conditions.append("bin.item_code in %(items)s")
		values["items"] = tuple(item_codes)
	if batch_nos:
		conditions.append("sbe.batch_no in %(batches)s")
		values["batches"] = tuple(batch_nos)

	batched = frappe.db.sql(
		f"""select sbe.warehouse, sbe.item_code, sbe.batch_no, sum(sbe.qty) as qty,
			sum(sbe.stock_value_difference) as value,
			min(case when sbe.qty > 0 then date(sbe.posting_datetime) end) as first_receipt
		from `tabSerial and Batch Entry` sbe
		join `tabWarehouse` wh on wh.name = sbe.warehouse
		where {" and ".join(conditions)}
		group by sbe.warehouse, sbe.item_code, sbe.batch_no
		having abs(sum(sbe.qty)) > 0.0001""",
		values,
		as_dict=True,
	)
	if batch_nos:
		return batched

	unbatched = frappe.db.sql(
		f"""select bin.warehouse, bin.item_code, null as batch_no, bin.actual_qty as qty,
			bin.stock_value as value, null as first_receipt
		from `tabBin` bin
		join `tabItem` item on item.name = bin.item_code
		join `tabWarehouse` wh on wh.name = bin.warehouse
		where {" and ".join(bin_conditions)}""",
		values,
		as_dict=True,
	)
	return batched + unbatched


def enrich(rows):
	"""Add item, batch and age details used by reports and alerts."""
	items = {r.item_code for r in rows}
	batches = {r.batch_no for r in rows if r.batch_no}
	item_info = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"name": ("in", list(items))},
			fields=["name", "item_name", "item_group", "stock_uom", "nir_regulatory_category", "nir_abc_class"],
		)
	} if items else {}
	batch_info = {
		b.name: b
		for b in frappe.get_all(
			"Batch",
			filters={"name": ("in", list(batches))},
			fields=["name", "expiry_date", "nir_mrp", "nir_mrp_uom", "creation"],
		)
	} if batches else {}

	for row in rows:
		item = item_info.get(row.item_code, frappe._dict())
		batch = batch_info.get(row.batch_no, frappe._dict())
		row.item_name, row.item_group, row.stock_uom = item.item_name, item.item_group, item.stock_uom
		row.regulatory_category, row.abc_class = item.nir_regulatory_category, item.nir_abc_class
		row.expiry_date, row.mrp, row.mrp_uom = batch.expiry_date, batch.nir_mrp, batch.nir_mrp_uom
		row.days_to_expiry = date_diff(row.expiry_date, today()) if row.expiry_date else None
		received = row.first_receipt or (getdate(batch.creation) if batch.creation else None)
		row.age_days = date_diff(today(), received) if received else None
		row.valuation_rate = flt(row.value) / flt(row.qty) if flt(row.qty) else 0
	return rows


def age_bucket(days):
	if days is None:
		return ""
	if days <= 30:
		return "0-30"
	if days <= 90:
		return "31-90"
	if days <= 180:
		return "91-180"
	return "180+"
