"""Held stock (QC, recall, legal) cannot be picked, reserved or billed, and moves only into holding zones (WH-05)."""

import frappe
from frappe import _

from pharmacy.overrides.quarantine import get_non_sellable
from pharmacy.overrides.shelf_life import get_row_batches


def get_active_holds(item_codes):
	if not item_codes:
		return []
	return frappe.get_all(
		"Stock Hold",
		filters={"status": "Active", "item_code": ("in", list(item_codes))},
		fields=["name", "hold_type", "item_code", "batch_no", "warehouse"],
	)


def find_hold(holds, item_code, batches, warehouse):
	"""The first active hold covering this item, any of these batches and this warehouse."""
	for hold in holds:
		if hold.item_code != item_code:
			continue
		if hold.batch_no and hold.batch_no not in batches:
			continue
		if hold.warehouse and not within(warehouse, hold.warehouse):
			continue
		return hold


def within(warehouse, parent):
	if not warehouse:
		return False
	if warehouse == parent:
		return True
	lft, rgt = frappe.get_cached_value("Warehouse", parent, ["lft", "rgt"])
	return bool(frappe.db.exists("Warehouse", {"name": warehouse, "lft": (">", lft), "rgt": ("<", rgt)}))


def block_held_allocation(doc, method=None):
	if doc.get("is_return") or doc.get("is_consolidated"):
		return
	if doc.doctype == "Sales Invoice" and not doc.update_stock:
		return

	if doc.doctype == "Stock Reservation Entry":
		rows = [frappe._dict(idx=0, item_code=doc.item_code, warehouse=doc.warehouse, batch_no=None)]
	elif doc.doctype == "Pick List":
		rows = doc.locations
	else:
		rows = doc.items

	holds = get_active_holds({r.item_code for r in rows})
	if not holds:
		return

	blocked = []
	for row in rows:
		batches = get_row_batches(row) if row.get("batch_no") or row.get("serial_and_batch_bundle") else []
		# a line without a batch is blocked only by holds on the whole item
		applicable = holds if batches else [h for h in holds if not h.batch_no]
		hold = find_hold(applicable, row.item_code, batches, row.warehouse)
		if hold:
			blocked.append(f"#{row.idx} {row.item_code} — {hold.hold_type} hold {hold.name}")
	if blocked:
		frappe.throw("<br>".join(blocked), title=_("Stock on hold"))


def block_held_movement(doc, method=None):
	"""Held stock may go only into Quarantine / Returns / Expired zones, or be issued from them."""
	holds = get_active_holds({r.item_code for r in doc.items if r.s_warehouse})
	if not holds:
		return

	non_sellable = get_non_sellable({r.s_warehouse for r in doc.items} | {r.t_warehouse for r in doc.items})
	blocked = []
	for row in doc.items:
		if not row.s_warehouse:
			continue
		hold = find_hold(holds, row.item_code, get_row_batches(row), row.s_warehouse)
		if not hold:
			continue
		into_holding = row.t_warehouse in non_sellable
		issued_from_holding = not row.t_warehouse and row.s_warehouse in non_sellable
		if not (into_holding or issued_from_holding):
			blocked.append(f"#{row.idx} {row.item_code} — {hold.hold_type} hold {hold.name}")
	if blocked:
		frappe.throw(
			_("Held stock can only move into Quarantine, Returns or Expired zones:") + "<br>" + "<br>".join(blocked),
			title=_("Stock on hold"),
		)
