# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.communication.email import make
from frappe.model.document import Document

from pharmacy.overrides.po_dispatch import get_supplier_email


class ReceiptDiscrepancy(Document):
	def before_submit(self):
		missing = [f"#{row.idx} {row.item_code}" for row in self.items if row.discrepancy_type == "Damage" and not row.photo]
		if missing:
			frappe.throw(_("Attach a photo for each damaged line: {0}").format(", ".join(missing)))

	def on_submit(self):
		frappe.db.set_value("Purchase Receipt", self.purchase_receipt, "nir_receipt_discrepancy", self.name)
		self.db_set("email_status", self.send_to_supplier())

	def send_to_supplier(self):
		recipient = get_supplier_email(self)
		if not recipient:
			self.add_comment("Comment", _("Discrepancy note not emailed: no email address on the supplier"))
			return "Failed"
		try:
			make(
				doctype=self.doctype,
				name=self.name,
				recipients=recipient,
				subject=_("Receipt discrepancy {0} for your delivery against {1}").format(self.name, self.purchase_receipt),
				content=_("<p>Please find attached our discrepancy note for goods received on {0}.</p><p>{1}</p>").format(
					frappe.format(self.posting_date, "Date"), frappe.utils.escape_html(self.remarks or "")
				),
				send_email=True,
				print_format=frappe.get_meta(self.doctype).default_print_format or "Standard",
			)
		except frappe.OutgoingEmailError:
			self.add_comment("Comment", _("Discrepancy note not emailed: outgoing email is not set up"))
			return "Failed"
		return "Sent"
