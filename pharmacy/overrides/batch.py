import frappe
from erpnext.stock.get_item_details import get_conversion_factor
from frappe import _
from frappe.utils import flt, getdate, today

from pharmacy.pharmacy.doctype.nppa_ceiling_price.nppa_ceiling_price import get_active_ceiling_price


def set_batch_id(doc, method=None):
	"""Name new batches {item}-{supplier batch no}, keeping the supplier's number as printed.

	Batches created from a receipt arrive with batch_id already set and are referenced by it,
	so those keep their name and only record the supplier batch number.
	"""
	if doc.batch_id:
		doc.supplier_batch_no = doc.supplier_batch_no or doc.batch_id
		return

	if not doc.supplier_batch_no:
		return

	batch_id = f"{doc.item}-{doc.supplier_batch_no.strip()}"
	if frappe.db.exists("Batch", batch_id):
		frappe.throw(_("Batch {0} already exists").format(batch_id), frappe.DuplicateEntryError)

	doc.batch_id = batch_id


def validate_batch(doc, method=None):
	# MRP and expiry are enforced when stock is received (see stock_inward), because
	# ERPNext creates batches during receipts with nothing but the item filled in
	if not doc.nir_mrp:
		return

	if not doc.nir_mrp_uom:
		sales_uom, stock_uom = frappe.db.get_value("Item", doc.item, ["sales_uom", "stock_uom"])
		doc.nir_mrp_uom = sales_uom or stock_uom

	validate_nppa_ceiling(doc)


def validate_nppa_ceiling(doc):
	"""MRP may not exceed the NPPA ceiling (per stock unit, excl. GST) for the pack, plus GST."""
	if not frappe.db.get_value("Item", doc.item, "nir_nppa_controlled"):
		return

	# the ceiling in force when the batch was made applies, not today's
	on_date = doc.manufacturing_date or today()
	ceiling = get_active_ceiling_price(doc.item, on_date=on_date)
	if ceiling is None:
		return

	units_per_pack = flt(get_conversion_factor(doc.item, doc.nir_mrp_uom).get("conversion_factor")) or 1
	gst_rate = get_gst_rate(doc.item, on_date)
	max_mrp = flt(ceiling * units_per_pack * (1 + gst_rate / 100), 2)

	if flt(doc.nir_mrp, 2) > max_mrp:
		frappe.throw(
			_(
				"MRP {0} per {1} exceeds the NPPA limit of {2} ({3} per unit x {4} units, plus {5}% GST) for item {6}"
			).format(doc.nir_mrp, doc.nir_mrp_uom, max_mrp, ceiling, units_per_pack, gst_rate, doc.item),
			frappe.ValidationError,
		)


def get_gst_rate(item_code, on_date):
	"""GST rate from the item's tax template in force on the date; 0 if none is set."""
	rows = frappe.get_all(
		"Item Tax",
		filters={"parenttype": "Item", "parent": item_code},
		fields=["item_tax_template", "valid_from"],
		order_by="valid_from desc",
	)
	for row in rows:
		if not row.valid_from or getdate(row.valid_from) <= getdate(on_date):
			return flt(frappe.db.get_value("Item Tax Template", row.item_tax_template, "gst_rate"))

	return 0
