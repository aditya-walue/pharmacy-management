# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Tote(Document):
	def validate(self):
		# scanners send the label as printed; keep IDs in one canonical form
		self.tote_id = (self.tote_id or "").strip().upper()
