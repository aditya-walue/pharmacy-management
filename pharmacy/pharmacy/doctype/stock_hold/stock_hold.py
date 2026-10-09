# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

HOLD_ROLES = ("Compliance Pharmacist", "Warehouse Manager", "Category Manager", "System Manager")


class StockHold(Document):
	def validate(self):
		if self.batch_no and frappe.db.get_value("Batch", self.batch_no, "item") != self.item_code:
			frappe.throw(_("Batch {0} is not of item {1}").format(self.batch_no, self.item_code))
		if self.is_new():
			self.status = "Active"
			self.held_by = frappe.session.user
			self.held_on = now_datetime()


@frappe.whitelist()
def release_hold(stock_hold: str, remarks: str):
	if not set(HOLD_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted to release stock holds"), frappe.PermissionError)
	if not remarks:
		frappe.throw(_("Give a reason for releasing the hold"))

	hold = frappe.get_doc("Stock Hold", stock_hold)
	if hold.status != "Active":
		frappe.throw(_("{0} is already released").format(hold.name))
	hold.status = "Released"
	hold.released_by = frappe.session.user
	hold.released_on = now_datetime()
	hold.release_remarks = remarks
	hold.save(ignore_permissions=True)
	hold.add_comment("Comment", _("Released: {0}").format(remarks))
