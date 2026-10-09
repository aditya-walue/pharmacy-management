# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ControlledDrugRegister(Document):
	"""Statutory register: entries are written by the system and never changed; errors are reversed."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Register entries cannot be changed; post a reversing entry instead"))

	def on_trash(self):
		frappe.throw(_("Register entries cannot be deleted"))
