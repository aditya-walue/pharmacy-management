# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class NPPACeilingPrice(Document):
	def validate(self):
		if self.valid_upto and getdate(self.valid_upto) < getdate(self.valid_from):
			frappe.throw(_("Valid Upto cannot be before Valid From"), frappe.ValidationError)

		self.validate_overlap()

	def validate_overlap(self):
		"""An item may have only one ceiling price in force on any date."""
		if not self.item or not self.valid_from:
			return

		existing = frappe.get_all(
			"NPPA Ceiling Price",
			filters={"item": self.item, "name": ("!=", self.name)},
			fields=["name", "valid_from", "valid_upto"],
		)

		curr_from = getdate(self.valid_from)
		curr_upto = getdate(self.valid_upto) if self.valid_upto else None

		for record in existing:
			rec_from = getdate(record.valid_from)
			rec_upto = getdate(record.valid_upto) if record.valid_upto else None

			latest_start = max(curr_from, rec_from)
			earliest_end = None
			if curr_upto and rec_upto:
				earliest_end = min(curr_upto, rec_upto)
			elif curr_upto:
				earliest_end = curr_upto
			elif rec_upto:
				earliest_end = rec_upto

			if earliest_end is None or latest_start <= earliest_end:
				frappe.throw(
					_("Overlapping NPPA Ceiling Price {0} already exists for Item {1}").format(
						record.name, self.item
					),
					frappe.ValidationError,
				)


def get_active_ceiling_price(item_code, on_date=None):
	"""Returns the active NPPA ceiling price for an item on a given date (defaults to today)."""
	if not on_date:
		on_date = today()
	on_date = getdate(on_date)

	records = frappe.get_all(
		"NPPA Ceiling Price",
		filters={"item": item_code},
		fields=["ceiling_price", "valid_from", "valid_upto"],
		order_by="valid_from desc",
	)

	for record in records:
		rec_from = getdate(record.valid_from)
		rec_upto = getdate(record.valid_upto) if record.valid_upto else None
		if rec_from <= on_date:
			if rec_upto is None or rec_upto >= on_date:
				return flt(record.ceiling_price)

	return None
