# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ShelfLifeRule(Document):
	def validate(self):
		if self.applies_to == "Item Group":
			self.regulatory_category = None
			if not self.item_group:
				frappe.throw(_("Item Group is required when Applies To is Item Group"), frappe.ValidationError)
		else:
			self.item_group = None
			if not self.regulatory_category:
				frappe.throw(_("Regulatory Category is required when Applies To is Regulatory Category"), frappe.ValidationError)

		self.validate_duplicate()

	def validate_duplicate(self):
		if self.disabled:
			return

		target = "item_group" if self.applies_to == "Item Group" else "regulatory_category"
		duplicate = frappe.db.exists(
			"Shelf Life Rule",
			{
				"applies_to": self.applies_to,
				target: self.get(target),
				"disabled": 0,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("Active Shelf Life Rule {0} already exists for {1}").format(duplicate, self.get(target)),
				frappe.DuplicateEntryError,
			)
