"""Schedule X and NDPS: locked cage custody and Controlled Drug Register entries."""

import frappe
from frappe import _
from frappe.utils import flt

from pharmacy.overrides.warehouse_layout import get_layout, is_cage

CONTROLLED_CATEGORIES = ("Schedule X", "NDPS")
CUSTODIAN_ROLE = "Compliance Pharmacist"


def require_custodian(doc, method=None):
	"""before_submit: only the cage custodian may move stock into or out of the cage."""
	if doc.doctype == "Sales Invoice" and not doc.update_stock:
		return

	fields = ("warehouse", "rejected_warehouse", "s_warehouse", "t_warehouse")
	warehouses = {row.get(f) for row in doc.items for f in fields if row.get(f)}
	layout = get_layout(doc.company)
	caged = sorted(w for w in warehouses if is_cage(w, layout))
	if caged and CUSTODIAN_ROLE not in frappe.get_roles():
		frappe.throw(
			_("Only a {0} can move stock in or out of the locked cage ({1})").format(CUSTODIAN_ROLE, ", ".join(caged)),
			title=_("Cage custodian required"),
		)


def record_receipt(doc, method=None):
	"""GRN submit: one register line per received Schedule X / NDPS batch."""
	if doc.is_return:
		return
	invoices = (
		frappe.db.get_value("Gate Entry", doc.nir_gate_entry, "supplier_invoice_no") if doc.get("nir_gate_entry") else None
	) or doc.get("supplier_delivery_note")

	for row, category in controlled_rows(doc):
		post(
			doc,
			row,
			category,
			"Receipt",
			qty_in=flt(row.stock_qty),
			party_type="Supplier",
			party=doc.supplier,
			supplier_invoice_no=invoices,
		)


def reverse_receipt(doc, method=None):
	"""GRN cancel: the register is never edited, so the receipt is reversed by a new line."""
	if doc.is_return:
		return
	for row, category in controlled_rows(doc):
		post(doc, row, category, "Receipt Reversal", qty_out=flt(row.stock_qty), party_type="Supplier", party=doc.supplier)


def controlled_rows(doc):
	categories = dict(
		frappe.get_all(
			"Item",
			filters={
				"name": ("in", list({row.item_code for row in doc.items})),
				"nir_regulatory_category": ("in", CONTROLLED_CATEGORIES),
			},
			fields=["name", "nir_regulatory_category"],
			as_list=True,
		)
	)
	return [(row, categories[row.item_code]) for row in doc.items if row.item_code in categories and flt(row.stock_qty)]


def post(doc, row, category, transaction_type, qty_in=0, qty_out=0, **extra):
	# the H1 register records sales only; a running balance is kept for X / NDPS stock registers
	previous = None if category == "Schedule H1" else frappe.db.get_value(
		"Controlled Drug Register",
		{"register_type": category, "company": doc.company, "item_code": row.item_code},
		"balance_qty",
		order_by="creation desc",
	)
	frappe.get_doc(
		{
			"doctype": "Controlled Drug Register",
			"register_type": category,
			"posting_date": doc.posting_date,
			"transaction_type": transaction_type,
			"company": doc.company,
			"item_code": row.item_code,
			"batch_no": row.batch_no,
			"expiry_date": frappe.db.get_value("Batch", row.batch_no, "expiry_date") if row.batch_no else None,
			"voucher_type": doc.doctype,
			"voucher_no": doc.name,
			"warehouse": row.warehouse,
			"qty_in": qty_in,
			"qty_out": qty_out,
			"balance_qty": 0 if category == "Schedule H1" else flt(previous) + qty_in - qty_out,
			"stock_uom": row.stock_uom,
			"recorded_by": frappe.session.user,
			**extra,
		}
	).insert(ignore_permissions=True)


def record_sale(doc, method=None):
	"""Bill submit: Schedule H1 register line per H1 item; Sale lines for Schedule X / NDPS."""
	_post_sale(doc, "Sale")


def reverse_sale(doc, method=None):
	"""Bill cancel: registers are never edited, so the sale is reversed by a new line."""
	_post_sale(doc, "Sale Reversal")


def _post_sale(doc, transaction_type):
	from pharmacy.overrides.prescription import REGISTER_CATEGORIES, get_categories, is_retail_bill

	if not is_retail_bill(doc):
		return
	categories = get_categories(doc)
	details = {
		"party_type": "Customer", "party": doc.customer, "patient_name": doc.get("nir_patient_name"),
		"patient_address": doc.get("nir_patient_address"), "doctor_name": doc.get("nir_doctor_name"),
		"doctor_reg_no": doc.get("nir_doctor_reg_no"), "prescription": doc.get("nir_prescription"),
	}
	for row in doc.items:
		category = categories.get(row.item_code)
		if category not in REGISTER_CATEGORIES:
			continue
		qty = flt(row.stock_qty) or flt(row.qty)
		if transaction_type == "Sale":
			post(doc, row, category, "Sale", qty_out=qty, **details)
		else:
			post(doc, row, category, "Sale Reversal", qty_in=qty, **details)
