import frappe
from frappe import _

RX_CATEGORIES = {"Schedule H", "Schedule H1", "Schedule X", "NDPS"}


def set_default_hsn_for_tests(doc, method=None):
	if frappe.flags.in_test and not doc.gst_hsn_code:
		doc.gst_hsn_code = "30049099"
		if not doc.nir_regulatory_category:
			doc.nir_regulatory_category = "OTC"
		if not doc.nir_storage_condition:
			doc.nir_storage_condition = "Ambient"


def validate_item(doc, method=None):
	"""Enforce pharmacy compliance rules on Item."""
	if doc.is_stock_item:
		# ERPNext blocks changing these once an item has stock, so only new items get them.
		# Batches are the supplier's numbers; auto-created ones would have no MRP and fail receipt.
		if doc.is_new():
			doc.has_batch_no = 1
			doc.has_expiry_date = 1
			doc.create_new_batch = 0

		if not doc.nir_regulatory_category:
			frappe.throw(
				_("Regulatory Category (nir_regulatory_category) is mandatory for stock items."),
				frappe.ValidationError,
			)

		if not doc.nir_storage_condition:
			frappe.throw(
				_("Storage Condition (nir_storage_condition) is mandatory for stock items."),
				frappe.ValidationError,
			)

	if doc.nir_regulatory_category in RX_CATEGORIES:
		doc.nir_rx_required = 1
	else:
		doc.nir_rx_required = 0
