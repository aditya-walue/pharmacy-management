# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PickFace(Document):
	def validate(self):
		if flt(self.max_qty) <= flt(self.min_qty):
			frappe.throw(_("Fill Up To must be more than Top Up Below"))
		if frappe.db.get_value("Warehouse", self.warehouse, "is_group"):
			frappe.throw(_("A pick face must be a bin, not a group warehouse"))
		duplicate = frappe.db.exists(
			"Pick Face",
			{"warehouse": self.warehouse, "item_code": self.item_code, "disabled": 0, "name": ("!=", self.name)},
		)
		if duplicate and not self.disabled:
			frappe.throw(_("{0} already defines this pick face").format(duplicate), frappe.DuplicateEntryError)
