"""Quarantined stock cannot be allocated, sold or moved out except through a QA Quarantine Decision.

Warehouses in Quarantine, Returns or Expired zones (or under one) are non-sellable. They also carry
ERPNext's is_rejected_warehouse flag, which keeps them out of Pick List allocation natively.
"""

import frappe
from frappe import _
from frappe.utils import flt

NON_SELLABLE_ZONES = ("Quarantine", "Returns", "Expired")


def sync_non_sellable(doc=None, method=None):
	"""Recompute the non-sellable mark for every warehouse; a zone's type applies to the bins under it."""
	warehouses = frappe.get_all(
		"Warehouse",
		fields=["name", "lft", "rgt", "nir_zone_type", "nir_non_sellable", "is_rejected_warehouse"],
		order_by="lft asc",
	)
	for warehouse in warehouses:
		ancestors = [w for w in warehouses if w.lft <= warehouse.lft and w.rgt >= warehouse.rgt]
		zone = next((w.nir_zone_type for w in reversed(ancestors) if w.nir_zone_type), None)
		non_sellable = int(zone in NON_SELLABLE_ZONES)
		if non_sellable == warehouse.nir_non_sellable:
			continue

		values = {"nir_non_sellable": non_sellable}
		# only undo the rejected flag if we set it; a user-flagged rejected warehouse stays rejected
		if non_sellable or warehouse.nir_non_sellable:
			values["is_rejected_warehouse"] = non_sellable
		frappe.db.set_value("Warehouse", warehouse.name, values, update_modified=False)


def get_non_sellable(warehouses):
	warehouses = {w for w in warehouses if w}
	if not warehouses:
		return set()
	return set(
		frappe.get_all(
			"Warehouse", filters={"name": ("in", list(warehouses)), "nir_non_sellable": 1}, pluck="name"
		)
	)


def block_allocation(doc, method=None):
	"""Sales and allocation documents may not draw on non-sellable warehouses."""
	if doc.get("is_return") or doc.get("is_consolidated"):
		return

	if doc.doctype == "Sales Invoice" and not doc.update_stock:
		return

	if doc.doctype == "Stock Reservation Entry":
		rows = [(0, doc.item_code, doc.warehouse)]
	elif doc.doctype == "Pick List":
		rows = [(row.idx, row.item_code, row.warehouse) for row in doc.locations]
	else:
		rows = [(row.idx, row.item_code, row.warehouse) for row in doc.items]

	blocked_warehouses = get_non_sellable(w for _idx, _item, w in rows)
	blocked = [f"#{idx} {item} ({warehouse})" for idx, item, warehouse in rows if warehouse in blocked_warehouses]
	if blocked:
		frappe.throw(
			_("Stock in quarantine, returns or expired zones cannot be allocated: {0}").format(", ".join(blocked)),
			title=_("Non-sellable stock"),
		)


def block_stock_entry(doc, method=None):
	"""Stock leaves a non-sellable zone only by a QA Quarantine Decision or into another holding zone."""
	sources = get_non_sellable(row.s_warehouse for row in doc.items)
	if not sources:
		return

	if released_by_qa(doc):
		return

	targets = get_non_sellable(row.t_warehouse for row in doc.items)
	blocked = [
		f"#{row.idx} {row.item_code} ({row.s_warehouse})"
		for row in doc.items
		if row.s_warehouse in sources and row.t_warehouse not in targets
	]
	if blocked:
		frappe.throw(
			_("Stock leaves quarantine only through a QA Quarantine Decision: {0}").format(", ".join(blocked)),
			title=_("QA release required"),
		)


def released_by_qa(doc):
	if not doc.get("nir_quarantine_decision"):
		return False

	decision = frappe.db.get_value(
		"Quarantine Decision",
		doc.nir_quarantine_decision,
		["docstatus", "item_code", "quarantine_warehouse", "qty"],
		as_dict=True,
	)
	if not decision or decision.docstatus != 1:
		return False
	return all(
		row.item_code == decision.item_code
		and row.s_warehouse == decision.quarantine_warehouse
		and flt(row.transfer_qty or row.qty) <= flt(decision.qty) + 0.0001
		for row in doc.items
		if row.s_warehouse
	)
