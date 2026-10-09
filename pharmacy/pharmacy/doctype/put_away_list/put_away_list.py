# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PutawayList(Document):
	def validate(self):
		if self.docstatus == 0:
			self.status = "In Progress" if any(row.confirmed for row in self.items) else "Pending"

	def before_submit(self):
		pending = [f"#{row.idx} {row.item_code}" for row in self.items if not (row.confirmed and row.actual_bin)]
		if pending:
			frappe.throw(_("Scan the bin for every line before submitting: {0}").format(", ".join(pending)))

	def on_submit(self):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"company": self.company,
				"remarks": _("Put-away {0} for {1}").format(self.name, self.purchase_receipt),
				"items": [
					{
						"item_code": row.item_code,
						"qty": flt(row.qty),
						"s_warehouse": row.source_warehouse,
						"t_warehouse": row.actual_bin,
						"batch_no": row.batch_no,
						"use_serial_batch_fields": 1,
					}
					for row in self.items
				],
			}
		)
		entry.insert()
		entry.submit()
		self.db_set({"stock_entry": entry.name, "status": "Completed"})

	def on_cancel(self):
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			frappe.get_doc("Stock Entry", self.stock_entry).cancel()
		self.db_set("status", "Cancelled")


@frappe.whitelist()
def confirm_scan(putaway: str, code: str, bin_code: str):
	"""Scan a batch (or item) label, then the bin it went into; marks the first matching open line."""
	doc = frappe.get_doc("Put-away List", putaway)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted").format(doc.name))

	code, bin_code = (code or "").strip(), (bin_code or "").strip()
	if not frappe.db.exists("Warehouse", {"name": bin_code, "is_group": 0}):
		frappe.throw(_("{0} is not a bin").format(bin_code))

	item_code = frappe.db.get_value("Item Barcode", {"barcode": code}, "parent") or code
	row = next(
		(r for r in doc.items if not r.confirmed and (r.batch_no == code or r.item_code == item_code)), None
	)
	if not row:
		frappe.throw(_("No open line for {0} on this list").format(code))

	row.actual_bin = bin_code
	row.confirmed = 1
	doc.save()
	return {"idx": row.idx, "item_code": row.item_code, "bin": bin_code, "moved": bin_code != row.suggested_bin}
