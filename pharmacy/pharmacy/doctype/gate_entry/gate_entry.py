# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GateEntry(Document):
	def validate(self):
		if self.purchase_order:
			details = get_po_details(self.purchase_order)
			if self.supplier and self.supplier != details["supplier"]:
				frappe.throw(_("Purchase Order {0} is from {1}, not {2}").format(self.purchase_order, details["supplier"], self.supplier))
			for field, value in details.items():
				if not self.get(field):
					self.set(field, value)

	def on_submit(self):
		self.db_set("status", "Arrived")

	def before_cancel(self):
		receipts = frappe.get_all(
			"Purchase Receipt", filters={"nir_gate_entry": self.name, "docstatus": 1}, pluck="name"
		)
		if receipts:
			frappe.throw(_("Cancel Purchase Receipts {0} first").format(", ".join(receipts)))

	def on_cancel(self):
		self.db_set("status", "Cancelled")


@frappe.whitelist()
def get_po_details(purchase_order: str) -> dict:
	"""Supplier, company and receiving DC of an open PO; a PO for a bin is received at the bin's DC."""
	from pharmacy.overrides.warehouse_layout import get_layout

	po = frappe.db.get_value(
		"Purchase Order", purchase_order, ["supplier", "company", "set_warehouse", "docstatus", "status"], as_dict=True
	)
	if not po or po.docstatus != 1 or po.status not in ("To Receive", "To Receive and Bill"):
		frappe.throw(_("Purchase Order {0} is not submitted or not awaiting goods").format(purchase_order))
	warehouse = po.set_warehouse or frappe.db.get_value("Purchase Order Item", {"parent": purchase_order}, "warehouse")
	site = get_layout(po.company).get(warehouse, frappe._dict()).site or warehouse
	return {"supplier": po.supplier, "company": po.company, "warehouse": site}


@frappe.whitelist()
def make_purchase_receipt(source_name: str, target_doc=None):
	"""GRN for the gate entry's PO, with the gate entry and supplier invoice already filled in."""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt as from_po

	gate = frappe.get_doc("Gate Entry", source_name)
	gate.check_permission("read")
	if gate.docstatus != 1:
		frappe.throw(_("Submit the Gate Entry first"))
	if not gate.purchase_order:
		frappe.throw(_("Gate Entry {0} has no Purchase Order; create the receipt from the PO").format(gate.name))

	receipt = from_po(gate.purchase_order)
	receipt.nir_gate_entry = gate.name
	receipt.supplier_delivery_note = gate.supplier_invoice_no
	receipt.lr_no = gate.vehicle_no
	return receipt
