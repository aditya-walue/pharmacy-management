"""DC layout: warehouse tree with each node's effective role, zone type and storage condition.

Zone type and storage condition are inherited: a bin with none of its own takes its nearest ancestor's.
"""

import frappe
from frappe.utils import flt

CAGE_ZONE = "Scheduled Drug Cage"
RECEIVING_ZONE = "Receiving"


def get_layout(company=None):
	"""All warehouses (optionally of one company) with inherited zone_type and storage_condition."""
	filters = {"company": company} if company else {}
	warehouses = frappe.get_all(
		"Warehouse",
		filters=filters,
		fields=[
			"name", "lft", "rgt", "is_group", "disabled", "nir_warehouse_role", "nir_zone_type",
			"nir_storage_condition", "nir_bin_capacity", "nir_non_sellable",
		],
		order_by="lft asc",
	)
	stack = []
	for warehouse in warehouses:
		while stack and stack[-1].rgt < warehouse.lft:
			stack.pop()
		parent = stack[-1] if stack else None
		warehouse.zone_type = warehouse.nir_zone_type or (parent.zone_type if parent else None)
		warehouse.storage_condition = warehouse.nir_storage_condition or (parent.storage_condition if parent else None)
		warehouse.site = (
			warehouse.name if warehouse.nir_warehouse_role == "DC" or not parent else parent.site
		)
		stack.append(warehouse)
	return {w.name: w for w in warehouses}


def get_zone_type(warehouse):
	return get_layout().get(warehouse, frappe._dict()).get("zone_type")


def is_cage(warehouse, layout=None):
	layout = layout or get_layout()
	return bool(warehouse) and layout.get(warehouse, frappe._dict()).get("zone_type") == CAGE_ZONE


def get_bin_stock(warehouses):
	if not warehouses:
		return {}
	return dict(
		frappe.db.sql(
			"select warehouse, sum(actual_qty) from `tabBin` where warehouse in %s group by warehouse",
			[tuple(warehouses)],
		)
	)


def get_item_bins(item_code, warehouses):
	if not warehouses:
		return set()
	return set(
		frappe.get_all(
			"Bin",
			filters={"item_code": item_code, "warehouse": ("in", list(warehouses)), "actual_qty": (">", 0)},
			pluck="warehouse",
		)
	)


def free_capacity(warehouse, stock, planned):
	capacity = flt(warehouse.nir_bin_capacity)
	if not capacity:
		return None  # unlimited
	return capacity - flt(stock.get(warehouse.name)) - flt(planned.get(warehouse.name))
