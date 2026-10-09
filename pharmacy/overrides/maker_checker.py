# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime

CONTROLLED_FIELDS = {
	"Item": [
		"nir_regulatory_category",
		"nir_storage_condition",
		"nir_salt",
		"nir_strength",
		"gst_hsn_code",
		"nir_nppa_controlled",
	],
	"Supplier": [
		"supplier_name",
		"supplier_type",
		"tax_id",
		"gstin",
		"nir_fssai_no",
		"nir_lead_time_days",
		"nir_moq_value",
		"nir_moq_qty",
		"nir_expiry_return_window_days",
		"nir_expiry_credit_pct",
		"nir_expiry_return_policy",
		"payment_terms",
	],
	"Customer": [
		"customer_name",
		"customer_type",
		"tax_id",
		"gstin",
	],
	"Replenishment Schedule": [
		"scope",
		"store",
		"item",
		"item_group",
		"frequency",
		"reorder_level",
		"reorder_qty",
	],
	"Pharmacy Store": [
		"store_name",
		"warehouse",
		"serving_warehouse",
		"cluster",
		"route",
		"store_grade",
		"drug_licence",
		"gstin",
	],
}


def process_maker_checker(doc, method=None):
	"""Hook for validate on Item, Supplier, Customer, Batch, Item Price, Replenishment Schedule."""
	current_user = frappe.session.user

	if doc.is_new():
		if not doc.get("nir_maker"):
			doc.nir_maker = doc.get("owner") or current_user

		if doc.get("nir_approval_status") == "Approved":
			doc.nir_approved_by = current_user
			doc.nir_approved_on = now_datetime()
			if hasattr(doc, "disabled") and doc.disabled is None:
				doc.disabled = 0
		else:
			doc.nir_approval_status = "Pending Approval"
			if hasattr(doc, "disabled"):
				doc.disabled = 1
		return

	old_doc = doc._doc_before_save
	old_status = old_doc.get("nir_approval_status") if old_doc else doc.db_get("nir_approval_status")

	# Case A: Transitioning from Pending/Draft -> Approved
	if doc.get("nir_approval_status") == "Approved" and old_status != "Approved":
		if doc.nir_maker and current_user == doc.nir_maker:
			frappe.throw(
				_("Maker cannot approve their own change. A separate checker must review and approve."),
				frappe.ValidationError,
			)

		doc.nir_approved_by = current_user
		doc.nir_approved_on = now_datetime()
		if hasattr(doc, "disabled"):
			doc.disabled = 0

		if doc.doctype == "Batch" and doc.get("nir_pending_mrp"):
			doc.nir_mrp = doc.nir_pending_mrp
			doc.nir_pending_mrp = None

		if doc.doctype == "Item Price" and doc.get("nir_pending_rate"):
			doc.price_list_rate = doc.nir_pending_rate
			doc.nir_pending_rate = None

	# Case B: Already Approved record being edited
	elif old_status == "Approved":
		if doc.doctype == "Batch" and doc.has_value_changed("nir_mrp"):
			doc.nir_pending_mrp = doc.nir_mrp
			doc.nir_mrp = old_doc.get("nir_mrp") if old_doc else doc.db_get("nir_mrp")
			doc.nir_approval_status = "Pending Approval"
			doc.nir_maker = current_user

		elif doc.doctype == "Item Price" and doc.has_value_changed("price_list_rate"):
			doc.nir_pending_rate = doc.price_list_rate
			doc.price_list_rate = old_doc.get("price_list_rate") if old_doc else doc.db_get("price_list_rate")
			doc.nir_approval_status = "Pending Approval"
			doc.nir_maker = current_user

		elif doc.doctype in CONTROLLED_FIELDS:
			changed = any(doc.has_value_changed(f) for f in CONTROLLED_FIELDS[doc.doctype])
			if changed:
				doc.nir_approval_status = "Pending Approval"
				doc.nir_maker = current_user
				if hasattr(doc, "disabled"):
					doc.disabled = 1
