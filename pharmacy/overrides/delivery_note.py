"""Delivery Note, Sales Order & Sales Invoice overrides for Pharmacy:
1. Prevent fractional quantities (e.g. 0.067 Strip) by auto-converting to stock UOM (Tablet) or whole integer.
2. Auto-allocate earliest-expiry batches (FEFO) if not manually selected.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from pharmacy.overrides.pos_billing import pick_batch, uom_factor
from pharmacy.overrides.stock_hold import get_active_holds


def validate_delivery_note(doc, method=None):
	"""Auto-fix fractional quantities and auto-pick sellable batches for Delivery Note."""
	holds = get_active_holds({r.item_code for r in doc.items})

	for row in doc.items:
		item = frappe.get_cached_value(
			"Item",
			row.item_code,
			["has_batch_no", "nir_loose_sale", "sales_uom", "stock_uom"],
			as_dict=True,
		)
		if not item:
			continue

		# Clear invalid serial_no if item has no serial tracking
		has_serial = frappe.get_cached_value("Item", row.item_code, "has_serial_no")
		if not has_serial and row.serial_no:
			row.serial_no = None

		# 1. Correct fractional UOM quantities (e.g. 0.067 Strip -> 1 Tablet)
		fix_fractional_qty(row, item)

		# 2. Auto-allocate batch if missing
		if item.has_batch_no and not row.batch_no and not doc.get("is_return"):
			try:
				row.batch_no = pick_batch(row, doc, holds)
				row.use_serial_batch_fields = 1
			except Exception as e:
				frappe.log_error(f"Auto-batch allocation failed for {row.item_code}: {e}", "Pharmacy DN Batch")


def validate_sales_order(doc, method=None):
	"""Prevent fractional quantities on Sales Order lines."""
	for row in doc.items:
		item = frappe.get_cached_value(
			"Item",
			row.item_code,
			["has_batch_no", "nir_loose_sale", "sales_uom", "stock_uom"],
			as_dict=True,
		)
		if not item:
			continue
		fix_fractional_qty(row, item)


def validate_sales_invoice(doc, method=None):
	"""Auto-fix fractional quantities and auto-pick batches on standard Sales Invoices."""
	holds = get_active_holds({r.item_code for r in doc.items})

	for row in doc.items:
		item = frappe.get_cached_value(
			"Item",
			row.item_code,
			["has_batch_no", "nir_loose_sale", "sales_uom", "stock_uom"],
			as_dict=True,
		)
		if not item:
			continue

		fix_fractional_qty(row, item)

		if item.has_batch_no and not row.batch_no and not doc.get("is_return"):
			try:
				row.batch_no = pick_batch(row, doc, holds)
				row.use_serial_batch_fields = 1
			except Exception as e:
				frappe.log_error(f"Auto-batch allocation failed for {row.item_code}: {e}", "Pharmacy SI Batch")


def fix_fractional_qty(row, item):
	"""
	Ensure items are not sold in fractional pack quantities like 0.067 Strips.
	If fractional quantity < 1 is detected on a pack UOM, convert line to stock_uom (Tablet).
	"""
	qty = flt(row.qty)
	factor = flt(row.conversion_factor) or 1.0

	# Case A: Fractional pack quantity (e.g. 0.067 Strip with factor 15)
	if 0 < qty < 1.0 and factor > 1.0:
		stock_qty = flt(row.stock_qty) or (qty * factor)
		target_qty = round(stock_qty) if round(stock_qty) >= 1.0 else 1.0

		row.uom = item.stock_uom or row.stock_uom or "Tablet"
		row.conversion_factor = 1.0
		row.qty = target_qty
		row.stock_qty = target_qty

		# Recalculate rate per single tablet if rate was per pack
		if flt(row.rate) > 0 and factor > 1.0:
			row.rate = flt(row.rate / factor, 2)
			row.amount = round(row.qty * row.rate, 2)

	# Case B: Fractional quantity on a UOM that requires whole numbers
	elif row.uom:
		must_be_whole = frappe.get_cached_value("UOM", row.uom, "must_be_whole_number")
		if must_be_whole and qty != round(qty):
			row.qty = max(1.0, round(qty))
			row.stock_qty = flt(row.qty) * factor
			row.amount = round(row.qty * flt(row.rate), 2)
