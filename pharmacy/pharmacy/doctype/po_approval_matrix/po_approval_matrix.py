# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class POApprovalMatrix(Document):
	def validate(self):
		# only the field matching Applies To is kept
		if self.applies_to != "Regulatory Category":
			self.regulatory_category = None
		if self.applies_to != "Item Group":
			self.item_group = None

		if flt(self.to_value) and flt(self.to_value) < flt(self.from_value):
			frappe.throw(_("To Value cannot be less than From Value"))
