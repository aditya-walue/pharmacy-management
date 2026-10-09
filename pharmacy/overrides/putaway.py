"""System-directed put-away: pick bins by category zone, storage condition and free capacity.

Stock is received into a Receiving-zone bin; submitting the GRN raises a Put-away List with suggested
bins, and staff confirm each line by scanning the bin. Schedule X and NDPS lines skip staging and go
straight into the locked cage at receipt.
"""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import get_ancestors_of
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.warehouse_layout import (
	CAGE_ZONE,
	RECEIVING_ZONE,
	free_capacity,
	get_bin_stock,
	get_item_bins,
	get_layout,
)

CAGED_CATEGORIES = ("Schedule X", "NDPS")
FMCG_GROUPS = ("FMCG", "Cosmetics")
# storage conditions a bin may have to hold an item, best fit first
COMPATIBLE = {"2-8C": ("2-8C",), "Below 25C": ("Below 25C", "2-8C"), "Ambient": ("Ambient", None, "Below 25C", "2-8C")}
PUTAWAY_ROLES = ("Warehouse Manager", "Inward QC Executive")


def get_target_zone(item):
	if item.nir_regulatory_category in CAGED_CATEGORIES:
		return CAGE_ZONE
	if item.nir_storage_condition == "2-8C":
		return "Cold Room"
	groups = {item.item_group, *get_ancestors_of("Item Group", item.item_group)} if item.item_group else set()
	if groups & set(FMCG_GROUPS):
		return "FMCG"
	return "General"


def suggest_bins(item_code, stock_qty, from_warehouse, planned=None, layout=None):
	"""[(bin, qty)] covering stock_qty; a None bin carries whatever no bin had room for."""
	layout = layout or get_layout()
	planned = planned if planned is not None else get_planned_qty()
	item = frappe.get_cached_value(
		"Item", item_code, ["item_group", "nir_regulatory_category", "nir_storage_condition"], as_dict=True
	)
	condition = item.nir_storage_condition or "Ambient"
	zone = get_target_zone(item)
	if from_warehouse not in layout:
		return [(None, flt(stock_qty))]
	site = layout[from_warehouse].site

	compatible = COMPATIBLE.get(condition, (condition,))
	bins = [
		w
		for w in layout.values()
		if w.site == site
		and not w.is_group
		and not w.disabled
		and not w.nir_non_sellable
		and w.zone_type == zone
		and w.storage_condition in compatible
	]
	stock = get_bin_stock([b.name for b in bins])
	holding = get_item_bins(item_code, [b.name for b in bins])

	def rank(b):
		free = free_capacity(b, stock, planned)
		return (
			b.name not in holding,  # consolidate with stock already there
			compatible.index(b.storage_condition),  # closest condition before colder ones
			-(free if free is not None else float("inf")),
			b.name,
		)

	allocation, remaining = [], flt(stock_qty)
	for b in sorted(bins, key=rank):
		if remaining <= 0:
			break
		free = free_capacity(b, stock, planned)
		take = remaining if free is None else min(remaining, max(free, 0))
		if take > 0:
			allocation.append((b.name, take))
			planned[b.name] = flt(planned.get(b.name)) + take
			remaining -= take
	if remaining > 0:
		allocation.append((None, remaining))
	return allocation


def get_planned_qty():
	"""Qty already promised to bins by open put-away lists, so two lists don't fill the same space."""
	return dict(
		frappe.db.sql(
			"""select pli.suggested_bin, sum(pli.qty) from `tabPut-away List Item` pli
			join `tabPut-away List` pl on pl.name = pli.parent
			where pl.docstatus = 0 and pli.suggested_bin is not null
			group by pli.suggested_bin"""
		)
	)


def route_from_dc(doc, row, item, layout):
	"""A line pointing at the DC itself (e.g. copied from the PO) goes to a real bin: temperature-controlled
	stock straight to a bin cold enough for it, everything else to the Receiving zone for put-away."""
	current = layout.get(row.warehouse)
	if not current or not current.is_group or item.nir_regulatory_category in CAGED_CATEGORIES:
		return []

	condition = item.nir_storage_condition or "Ambient"
	if condition != "Ambient":
		qty = (flt(row.qty) + flt(row.rejected_qty)) * (flt(row.conversion_factor) or 1)
		target = next((b for b, _qty in suggest_bins(row.item_code, qty, row.warehouse, layout=layout) if b), None)
	else:
		target = next(
			(w.name for w in layout.values()
			 if w.site == current.site and not w.is_group and not w.disabled and w.zone_type == RECEIVING_ZONE),
			None,
		)
	if not target:
		frappe.throw(
			_("No {0} bin under {1} to receive {2}. Set the line's Accepted Warehouse to a bin.").format(
				_("Receiving") if condition == "Ambient" else condition, row.warehouse, row.item_code
			),
			title=_("Bin needed"),
		)
	row.warehouse = target
	return [_("Received into {0}").format(target)]


def route_to_cage(doc, row, item, layout):
	"""Schedule X and NDPS go into the locked cage at receipt, never via staging."""
	if item.nir_regulatory_category not in CAGED_CATEGORIES or row.nir_quarantined:
		return []
	current = layout.get(row.warehouse)
	if current and current.zone_type == CAGE_ZONE:
		return []

	qty = (flt(row.qty) + flt(row.rejected_qty)) * (flt(row.conversion_factor) or 1)
	allocation = suggest_bins(row.item_code, qty, row.warehouse or doc.set_warehouse, layout=layout)
	cage = next((b for b, _qty in allocation if b), None)
	if not cage:
		frappe.throw(
			_("No Scheduled Drug Cage bin for {0} under the receiving DC").format(row.item_code),
			title=_("Cage bin missing"),
		)
	row.warehouse = cage
	return [_("Routed to cage {0}").format(cage)]


def make_putaway_list(doc, method=None):
	"""On GRN submit: a Put-away List for every line received into a Receiving zone."""
	if doc.is_return:
		return
	layout = get_layout(doc.company)
	staged = [row for row in doc.items if layout.get(row.warehouse, frappe._dict()).zone_type == RECEIVING_ZONE]
	if not staged:
		return

	planned = get_planned_qty()
	lines = []
	for row in staged:
		for bin_name, qty in suggest_bins(row.item_code, row.stock_qty, row.warehouse, planned, layout):
			lines.append(
				{
					"item_code": row.item_code,
					"batch_no": row.batch_no,
					"qty": qty,
					"source_warehouse": row.warehouse,
					"suggested_bin": bin_name,
					"actual_bin": bin_name,
				}
			)

	putaway = frappe.get_doc(
		{"doctype": "Put-away List", "company": doc.company, "purchase_receipt": doc.name, "items": lines}
	).insert(ignore_permissions=True)

	users = {u for role in PUTAWAY_ROLES for u in get_users_with_role(role)}
	for user in users:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Put-away List",
				"document_name": putaway.name,
				"subject": _("Put away {0} lines received on {1}").format(len(lines), doc.name),
			}
		).insert(ignore_permissions=True)
