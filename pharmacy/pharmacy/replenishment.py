# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from pharmacy.pharmacy.doctype.replenishment_schedule.replenishment_schedule import (
	get_effective_replenishment_schedule,
)


@frappe.whitelist()
def generate_replenishment_suggestions(
	store: str = None, posting_date: str = None, days_of_cover: int = 7, sales_history_days: int = 30
) -> list[dict]:
	"""Generate replenishment suggestions for a store based on schedule due dates, sales velocity, live stock, and transit stock."""
	frappe.has_permission("Pharmacy Store", "read", throw=True)

	date = getdate(posting_date) if posting_date else getdate(today())
	stores = get_target_stores(store)
	suggestions = []

	for store_doc in stores:
		store_wh = store_doc.warehouse
		dc_wh = store_doc.serving_warehouse
		cluster = store_doc.cluster

		items = get_replenishment_candidate_items()

		for item in items:
			item_code = item.name
			sched = get_effective_replenishment_schedule(item_code, store=store_doc.name, cluster=cluster)

			is_due = is_item_due_on_date(sched.get("frequency"), sched.get("order_days"), date)

			store_stock = get_store_stock(item_code, store_wh)
			transit_stock = get_stock_in_transit(item_code, store_wh)
			avg_daily_sales = get_avg_daily_sales(item_code, store_wh, date, days=sales_history_days)

			reorder_level = flt(sched.get("reorder_level") or 10.0)
			reorder_qty = flt(sched.get("reorder_qty") or 50.0)

			# Min/Max vs Days-of-cover target calculation
			target_from_cover = avg_daily_sales * flt(days_of_cover)
			target_stock = max(reorder_level + reorder_qty, target_from_cover)

			available_stock = store_stock + transit_stock
			needs_reorder = available_stock <= reorder_level

			suggested_qty = 0.0
			if needs_reorder:
				calc_qty = target_stock - available_stock
				suggested_qty = max(reorder_qty, calc_qty)

			action = "Not Due Today"
			if is_due:
				if needs_reorder:
					action = "Reorder"
				else:
					action = "Sufficient Stock"

			if is_due or needs_reorder:
				suggestions.append({
					"store": store_doc.name,
					"store_name": store_doc.store_name,
					"store_warehouse": store_wh,
					"serving_warehouse": dc_wh,
					"item_code": item_code,
					"item_name": item.item_name,
					"item_group": item.item_group,
					"regulatory_category": item.nir_regulatory_category,
					"frequency": sched.get("frequency"),
					"order_days": sched.get("order_days"),
					"is_due_today": 1 if is_due else 0,
					"store_stock": store_stock,
					"stock_in_transit": transit_stock,
					"available_stock": available_stock,
					"avg_daily_sales": round(avg_daily_sales, 2),
					"reorder_level": reorder_level,
					"reorder_qty": reorder_qty,
					"target_stock": round(target_stock, 2),
					"suggested_qty": round(suggested_qty, 2) if is_due and needs_reorder else 0.0,
					"suggested_action": action,
				})

	return suggestions


def is_item_due_on_date(frequency: str, order_days: str, date) -> bool:
	if not frequency or frequency == "Daily":
		return True

	day_name = date.strftime("%A")
	day_num = date.day
	weekday_num = date.weekday()

	if order_days and order_days != "Daily":
		days_list = [d.strip() for d in order_days.replace("&", ",").split(",") if d.strip()]
		if any(d.lower() in day_name.lower() for d in days_list):
			return True

	if frequency == "Alternate Days":
		return (date.toordinal() % 2) == 0

	if frequency == "Twice a Week":
		return weekday_num in (0, 3)

	if frequency == "Weekly":
		return weekday_num == 0

	if frequency == "Fortnightly":
		return day_num in (1, 15) or (weekday_num == 0 and (date.day // 7) in (0, 2))

	return True


def get_target_stores(store_name=None):
	filters = {"disabled": 0, "nir_approval_status": "Approved"}
	if store_name:
		filters["name"] = store_name
	return frappe.get_all("Pharmacy Store", filters=filters, fields=["name", "store_name", "warehouse", "serving_warehouse", "cluster"])


def get_replenishment_candidate_items():
	return frappe.get_all(
		"Item",
		filters={"is_stock_item": 1, "disabled": 0, "nir_approval_status": "Approved"},
		fields=["name", "item_name", "item_group", "nir_regulatory_category"],
	)


def get_store_stock(item_code, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0.0)


def get_stock_in_transit(item_code, target_warehouse):
	entries = frappe.db.sql(
		"""
		SELECT SUM(sed.qty)
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE sed.item_code = %s
		  AND sed.t_warehouse = %s
		  AND se.docstatus = 0
		  AND se.purpose = 'Material Transfer'
	""",
		(item_code, target_warehouse),
	)
	return flt(entries[0][0]) if entries and entries[0][0] else 0.0


def get_avg_daily_sales(item_code, warehouse, end_date, days=30):
	start_date = add_days(end_date, -days)
	qty = frappe.db.sql(
		"""
		SELECT SUM(actual_qty)
		FROM `tabStock Ledger Entry`
		WHERE item_code = %s
		  AND warehouse = %s
		  AND actual_qty < 0
		  AND posting_date BETWEEN %s AND %s
		  AND voucher_type IN ('Sales Invoice', 'POS Invoice')
	""",
		(item_code, warehouse, start_date, end_date),
	)
	total_sold = abs(flt(qty[0][0])) if qty and qty[0][0] else 0.0
	return total_sold / flt(days) if days > 0 else 0.0


@frappe.whitelist()
def create_replenishment_material_request(store: str, items: list = None, posting_date: str = None) -> dict:
	"""Create or update a single draft Material Request (indent) for all items due at a store on a given day."""
	frappe.has_permission("Material Request", "create", throw=True)

	date = getdate(posting_date) if posting_date else getdate(today())
	store_doc = frappe.get_doc("Pharmacy Store", store)
	company = frappe.db.get_value("Warehouse", store_doc.warehouse, "company")
	suggestions = generate_replenishment_suggestions(store=store, posting_date=posting_date)

	reorder_items = [s for s in suggestions if s["suggested_action"] == "Reorder" and s["suggested_qty"] > 0]
	if items:
		reorder_items = [s for s in reorder_items if s["item_code"] in items]

	if not reorder_items:
		frappe.msgprint(_("No items currently due for reorder at store {0} on {1}.").format(store_doc.store_name, date))
		return None

	# Check for existing Draft Material Request for this store & date to ensure ONE indent per day
	existing_mr_name = frappe.db.get_value(
		"Material Request",
		{
			"docstatus": 0,
			"material_request_type": "Material Transfer",
			"company": company,
			"schedule_date": date,
		},
		"name",
	)

	item_rows = [
		{
			"item_code": s["item_code"],
			"qty": s["suggested_qty"],
			"from_warehouse": store_doc.serving_warehouse,
			"warehouse": store_doc.warehouse,
			"schedule_date": date,
		}
		for s in reorder_items
	]

	if existing_mr_name:
		mr = frappe.get_doc("Material Request", existing_mr_name)
		mr.set("items", item_rows)
		mr.save()
	else:
		mr = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Material Transfer",
			"company": company,
			"schedule_date": date,
			"items": item_rows,
		}).insert()

	return {"name": mr.name, "items_count": len(mr.items)}


@frappe.whitelist()
def create_delivery_from_indent(material_request: str) -> dict:
	"""Create a single delivery document (Stock Entry of type Material Transfer) containing all items from an indent (Material Request)."""
	frappe.has_permission("Stock Entry", "create", throw=True)

	mr = frappe.get_doc("Material Request", material_request)
	if not mr.items:
		frappe.throw(_("Material Request {0} has no items.").format(material_request))

	from pharmacy.overrides.shelf_life import get_shelf_life_threshold

	stock_entry_items = []
	posting_date = getdate(today())

	for row in mr.items:
		item_code = row.item_code
		qty_needed = flt(row.qty)
		s_wh = row.from_warehouse
		t_wh = row.warehouse

		# Check if item uses batches
		has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")

		if has_batch:
			min_shelf_days = get_shelf_life_threshold(item_code, "min_days_store_dispatch") or 0

			# Query available batches in FEFO order (expiry_date ASC)
			available_batches = frappe.db.sql(
				"""
				SELECT b.name, b.expiry_date, SUM(sle.actual_qty) as qty
				FROM `tabStock Ledger Entry` sle
				JOIN `tabBatch` b ON b.name = sle.batch_no
				WHERE sle.item_code = %s AND sle.warehouse = %s AND b.disabled = 0
				GROUP BY b.name, b.expiry_date
				HAVING qty > 0
				ORDER BY b.expiry_date ASC
			""",
				(item_code, s_wh),
				as_dict=True,
			)

			allocated_qty = 0.0
			for batch in available_batches:
				if allocated_qty >= qty_needed:
					break

				if batch.expiry_date:
					rem_days = (getdate(batch.expiry_date) - posting_date).days
					if rem_days < min_shelf_days:
						continue

				take_qty = min(flt(batch.qty), qty_needed - allocated_qty)
				stock_entry_items.append({
					"item_code": item_code,
					"qty": take_qty,
					"s_warehouse": s_wh,
					"t_warehouse": t_wh,
					"batch_no": batch.name,
					"material_request": mr.name,
					"material_request_item": row.name,
				})
				allocated_qty += take_qty

			# If available stock was unbatched or insufficient batched stock, add remaining row
			if allocated_qty < qty_needed:
				rem_qty = qty_needed - allocated_qty
				stock_entry_items.append({
					"item_code": item_code,
					"qty": rem_qty,
					"s_warehouse": s_wh,
					"t_warehouse": t_wh,
					"material_request": mr.name,
					"material_request_item": row.name,
				})
		else:
			stock_entry_items.append({
				"item_code": item_code,
				"qty": qty_needed,
				"s_warehouse": s_wh,
				"t_warehouse": t_wh,
				"material_request": mr.name,
				"material_request_item": row.name,
			})

	se = frappe.get_doc({
		"doctype": "Stock Entry",
		"purpose": "Material Transfer",
		"stock_entry_type": "Material Transfer",
		"company": mr.company,
		"posting_date": posting_date,
		"items": stock_entry_items,
	}).insert()

	return {"name": se.name, "items_count": len(se.items), "material_request": mr.name}

