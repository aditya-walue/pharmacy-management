"""Validate warehouse storage conditions, scheduled-drug cage, and bin capacity."""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt


def validate_storage(doc, method=None):
	if doc.get("is_return"):
		return

	ancestor_cache = {}
	item_cache = {}

	for row, warehouse in get_target_warehouses(doc):
		item_code = row.get("item_code")
		if not item_code:
			continue

		if item_code not in item_cache:
			item_cache[item_code] = frappe.db.get_value(
				"Item",
				item_code,
				["nir_storage_condition", "nir_regulatory_category"],
				as_dict=True,
			)
		item_data = item_cache[item_code] or {}
		item_condition = item_data.get("nir_storage_condition")
		category = item_data.get("nir_regulatory_category")

		if warehouse not in ancestor_cache:
			ancestor_cache[warehouse] = get_warehouse_ancestors(warehouse)
		ancestors = ancestor_cache[warehouse]

		wh_condition = get_warehouse_storage_condition(ancestors)
		check_storage_compatibility(item_code, item_condition, wh_condition, warehouse)
		check_scheduled_drug_cage(item_code, category, ancestors, warehouse)


def validate_bin_capacity(doc, method=None):
	if doc.get("is_return"):
		return

	incoming_by_wh = {}
	for row, warehouse in get_target_warehouses(doc):
		qty = get_row_incoming_qty(row, doc.doctype)
		if doc.doctype == "Stock Reconciliation":
			# reconciled qty replaces the item's current qty instead of adding to it
			qty -= flt(frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": warehouse}, "actual_qty"))
		incoming_by_wh[warehouse] = incoming_by_wh.get(warehouse, 0.0) + qty

	bin_table = frappe.qb.DocType("Bin")
	for warehouse, incoming in incoming_by_wh.items():
		capacity = flt(frappe.db.get_value("Warehouse", warehouse, "nir_bin_capacity"))
		if capacity <= 0:
			continue

		res = (
			frappe.qb.from_(bin_table)
			.select(Sum(bin_table.actual_qty))
			.where(bin_table.warehouse == warehouse)
			.run()
		)
		current = flt(res[0][0]) if res and res[0][0] is not None else 0.0

		if current + incoming > capacity:
			frappe.throw(
				_("Bin capacity exceeded for {0}: current {1}, incoming {2}, capacity {3}").format(
					warehouse, current, incoming, capacity
				),
				title=_("Bin capacity exceeded"),
			)


def get_target_warehouses(doc):
	"""Yield (row, target_warehouse) for incoming stock movements."""
	if doc.doctype == "Purchase Receipt":
		default_wh = doc.get("set_warehouse")
		for row in doc.get("items") or []:
			wh = row.get("warehouse") or default_wh
			if wh:
				yield row, wh
	elif doc.doctype == "Purchase Invoice" and doc.get("update_stock"):
		default_wh = doc.get("set_warehouse")
		for row in doc.get("items") or []:
			wh = row.get("warehouse") or default_wh
			if wh:
				yield row, wh
	elif doc.doctype == "Stock Entry":
		for row in doc.get("items") or []:
			# stock in transit travels in sealed totes / insulated boxes, not in a bin
			if row.get("t_warehouse") and frappe.get_cached_value("Warehouse", row.t_warehouse, "warehouse_type") != "Transit":
				yield row, row.t_warehouse
	elif doc.doctype == "Stock Reconciliation":
		for row in doc.get("items") or []:
			if row.get("warehouse"):
				yield row, row.warehouse


def get_row_incoming_qty(row, doctype):
	if row.get("stock_qty") is not None:
		return flt(row.stock_qty)
	if doctype == "Stock Entry" and row.get("transfer_qty") is not None:
		return flt(row.transfer_qty)
	if row.get("qty") is not None:
		return flt(row.qty)
	return 0.0


def get_warehouse_ancestors(warehouse):
	"""Return list of ancestor warehouse dicts from warehouse up to root (self included)."""
	if not warehouse:
		return []

	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"]) or (None, None)
	if not lft or not rgt:
		w = frappe.db.get_value(
			"Warehouse",
			warehouse,
			["name", "nir_warehouse_role", "nir_zone_type", "nir_storage_condition", "nir_bin_capacity"],
			as_dict=True,
		)
		return [w] if w else []

	return frappe.get_all(
		"Warehouse",
		filters={"lft": ("<=", lft), "rgt": (">=", rgt)},
		order_by="lft desc",
		fields=["name", "nir_warehouse_role", "nir_zone_type", "nir_storage_condition", "nir_bin_capacity"],
	)


def get_warehouse_storage_condition(ancestors):
	for w in ancestors:
		if w.get("nir_storage_condition"):
			return w.nir_storage_condition
	return "Ambient"


def check_storage_compatibility(item_code, item_condition, wh_condition, warehouse):
	if not item_condition or item_condition == "Ambient":
		return

	if item_condition == "Below 25C":
		if wh_condition not in ("Below 25C", "2-8C"):
			frappe.throw(
				_("Item {0} requires Below 25C storage, but warehouse {1} has condition {2}.").format(
					item_code, warehouse, wh_condition
				),
				title=_("Incompatible storage condition"),
			)
	elif item_condition == "2-8C":
		if wh_condition != "2-8C":
			frappe.throw(
				_("Item {0} requires 2-8C storage, but warehouse {1} has condition {2}.").format(
					item_code, warehouse, wh_condition
				),
				title=_("Incompatible storage condition"),
			)


def check_scheduled_drug_cage(item_code, regulatory_category, ancestors, warehouse):
	if regulatory_category not in ("Schedule X", "NDPS"):
		return

	# Store warehouses are exempt from the cage rule
	if any(w.get("nir_warehouse_role") == "Store" for w in ancestors):
		return

	# Only when target is inside a DC layout (target or ancestor has role "Zone" or "Bin")
	if not any(w.get("nir_warehouse_role") in ("Zone", "Bin") for w in ancestors):
		return

	nearest_zone_type = next((w.nir_zone_type for w in ancestors if w.get("nir_zone_type")), None)
	if nearest_zone_type != "Scheduled Drug Cage":
		frappe.throw(
			_("Item {0} ({1}) must be stored in a Scheduled Drug Cage; warehouse {2} has zone type {3}.").format(
				item_code, regulatory_category, warehouse, nearest_zone_type or _("None")
			),
			title=_("Scheduled drug cage required"),
		)
