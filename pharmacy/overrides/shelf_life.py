"""Validate batch shelf life on receipt and dispatch transactions."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate


def validate_shelf_life(doc, method=None):
	if doc.get("is_return") or doc.get("is_consolidated"):
		return

	posting_date = getdate(doc.get("posting_date") or doc.get("transaction_date") or frappe.utils.today())
	items = doc.get("items") or []

	for row in items:
		if not row.get("item_code"):
			continue

		field_name = get_doc_rule_field(doc, row)
		if not field_name:
			continue

		batches = get_row_batches(row)
		if not batches:
			continue

		required_days = get_shelf_life_threshold(row.item_code, field_name)
		if required_days is None:
			continue

		for batch_no in batches:
			expiry_date = frappe.db.get_value("Batch", batch_no, "expiry_date")
			if not expiry_date:
				continue

			remaining_days = date_diff(getdate(expiry_date), posting_date)
			if remaining_days < required_days:
				frappe.throw(
					_("Item {0}, batch {1} has only {2} remaining days of shelf life (required: {3} days).").format(
						row.item_code, batch_no, remaining_days, required_days
					),
					title=_("Shelf life insufficient"),
				)


def get_doc_rule_field(doc, row):
	doctype = doc.doctype
	if doctype == "Purchase Receipt":
		return "min_days_supplier_receipt"
	if doctype == "Purchase Invoice" and doc.get("update_stock"):
		return "min_days_supplier_receipt"
	if doctype == "Stock Entry" and doc.get("purpose") == "Material Receipt":
		return "min_days_supplier_receipt"
	# the dispatch rule is for stock sent to our stores, not counter or customer sales; stores with
	# their own GSTIN are internal customers and receive stock on a Delivery Note or Sales Invoice
	if doctype == "Delivery Note" and doc.get("is_internal_customer"):
		return "min_days_store_dispatch"
	if doctype == "Sales Invoice" and doc.get("update_stock") and doc.get("is_internal_customer"):
		return "min_days_store_dispatch"
	if doctype == "Stock Entry" and doc.get("purpose") == "Material Transfer":
		if row.get("t_warehouse"):
			role = frappe.db.get_value("Warehouse", row.t_warehouse, "nir_warehouse_role")
			if role == "Store":
				return "min_days_store_dispatch"
	return None


def get_row_batches(row):
	"""Return distinct batch numbers for a row from row.batch_no and serial_and_batch_bundle."""
	batches = []
	if row.get("batch_no"):
		batches.append(row.batch_no)
	if row.get("serial_and_batch_bundle"):
		bundle_batches = frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": row.serial_and_batch_bundle},
			pluck="batch_no",
		)
		batches.extend([b for b in bundle_batches if b])
	return list(dict.fromkeys(batches))


def get_shelf_life_threshold(item_code, field_name):
	"""Return the required shelf life days (stricter of category rule and nearest ancestor group rule)."""
	item = frappe.db.get_value("Item", item_code, ["item_group", "nir_regulatory_category"], as_dict=True)
	if not item:
		return None

	candidates = []

	# (a) Regulatory Category rule
	if item.nir_regulatory_category:
		cat_days = frappe.db.get_value(
			"Shelf Life Rule",
			{
				"applies_to": "Regulatory Category",
				"regulatory_category": item.nir_regulatory_category,
				"disabled": 0,
			},
			field_name,
		)
		if cat_days is not None:
			candidates.append(cat_days)

	# (b) Nearest ancestor Item Group rule
	if item.item_group:
		lft, rgt = frappe.db.get_value("Item Group", item.item_group, ["lft", "rgt"]) or (None, None)
		if lft and rgt:
			ancestors = frappe.get_all(
				"Item Group",
				filters={"lft": ("<=", lft), "rgt": (">=", rgt)},
				order_by="lft desc",
				pluck="name",
			)
		else:
			ancestors = [item.item_group]

		rules = frappe.get_all(
			"Shelf Life Rule",
			filters={"applies_to": "Item Group", "item_group": ("in", ancestors), "disabled": 0},
			fields=["item_group", field_name],
		)
		rule_map = {r.item_group: r.get(field_name) for r in rules}
		for group in ancestors:
			if group in rule_map and rule_map[group] is not None:
				candidates.append(rule_map[group])
				break

	if not candidates:
		return None

	return max(candidates)
