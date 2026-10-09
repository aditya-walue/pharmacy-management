# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PharmacyStore(Document):
	def validate(self):
		self.validate_pincodes()

	def validate_pincodes(self):
		pincodes = [row.pincode.strip() for row in self.pincodes_served if row.pincode]
		if len(pincodes) != len(set(pincodes)):
			frappe.throw(_("Pincodes served cannot contain duplicates within the same store."), frappe.ValidationError)


def get_serving_store(pincode: str) -> dict | None:
	"""Return active, approved Pharmacy Store details serving a given pincode for online orders."""
	if not pincode:
		return None

	pincode = str(pincode).strip()

	child = frappe.qb.DocType("Pharmacy Store Pincode")
	parent = frappe.qb.DocType("Pharmacy Store")

	store = (
		frappe.qb.from_(parent)
		.join(child)
		.on(child.parent == parent.name)
		.select(
			parent.name,
			parent.store_name,
			parent.warehouse,
			parent.serving_warehouse,
			parent.cluster,
			parent.route,
			parent.store_grade,
			child.delivery_type,
		)
		.where(
			(child.pincode == pincode)
			& (child.is_active == 1)
			& (parent.disabled == 0)
			& (parent.nir_approval_status == "Approved")
		)
		.limit(1)
		.run(as_dict=True)
	)

	return store[0] if store else None
