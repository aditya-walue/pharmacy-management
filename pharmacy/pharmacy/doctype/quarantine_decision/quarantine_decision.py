# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class QuarantineDecision(Document):
	def before_submit(self):
		if not self.decision:
			frappe.throw(_("Record the QA decision before submitting"))

	def on_submit(self):
		if self.decision == "Release to Stock":
			# release moves the stock straight away; it is the point of the decision
			self.db_set("stock_entry", self.make_stock_entry("Material Transfer", self.target_warehouse, submit=True))
		elif self.decision == "Destroy":
			# destruction is witnessed and documented, so the issue is left in draft
			self.db_set("stock_entry", self.make_stock_entry("Material Issue"))
		else:
			self.db_set("return_receipt", self.make_supplier_return())
		self.add_comment("Comment", _("QA decision: {0}").format(self.decision))

	def make_stock_entry(self, purpose, target=None, submit=False):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": purpose,
				"company": self.company,
				# lets the stock leave quarantine and stands as the adjustment's approval
				"nir_quarantine_decision": self.name,
				"nir_reason_code": "QA Rejection" if purpose == "Material Issue" else None,
				"remarks": _("{0} per Quarantine Decision {1}").format(self.decision, self.name),
				"items": [
					{
						"item_code": self.item_code,
						"qty": flt(self.qty),
						"s_warehouse": self.quarantine_warehouse,
						"t_warehouse": target,
						"batch_no": self.batch_no,
						"use_serial_batch_fields": 1,
					}
				],
			}
		)
		entry.insert()
		if submit:
			entry.submit()
		return entry.name

	def make_supplier_return(self):
		"""Draft purchase return of just the quarantined qty, against the original receipt."""
		from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_return

		if not self.purchase_receipt:
			frappe.throw(_("Link the Purchase Receipt to return the stock to the supplier"))

		ret = make_purchase_return(self.purchase_receipt)
		ret.items = [
			row
			for row in ret.items
			if row.item_code == self.item_code
			and row.warehouse == self.quarantine_warehouse
			and (not self.batch_no or row.batch_no == self.batch_no)
		][:1]
		if not ret.items:
			frappe.throw(_("Could not find the quarantined line on {0}").format(self.purchase_receipt))
		row = ret.items[0]
		row.qty = -flt(self.qty) / (flt(row.conversion_factor) or 1)
		row.rejected_qty = 0
		ret.remarks = _("Return per Quarantine Decision {0}").format(self.name)
		ret.insert()
		return ret.name
