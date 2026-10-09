# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, now, today

from pharmacy.pharmacy.doctype.replenishment_schedule.replenishment_schedule import (
	get_effective_replenishment_schedule,
)
from pharmacy.pharmacy.replenishment import is_item_due_on_date


def validate_manual_indent(doc, method=None):
	"""Validate manual store indents and off-schedule items against Area Manager approval threshold limits."""
	if doc.material_request_type != "Material Transfer":
		return

	target_wh = None
	for row in doc.items:
		if row.warehouse:
			target_wh = row.warehouse
			break

	if not target_wh:
		return

	# Find Pharmacy Store for this warehouse
	store_doc = frappe.db.get_value(
		"Pharmacy Store",
		{"warehouse": target_wh, "disabled": 0},
		["name", "store_name", "cluster", "nir_manual_indent_limit", "nir_area_manager"],
		as_dict=True,
	)
	if not store_doc:
		return

	limit = flt(store_doc.nir_manual_indent_limit or 5000.0)
	posting_date = getdate(doc.schedule_date or doc.transaction_date or today())

	off_schedule_amount = 0.0
	is_manual = doc.get("nir_indent_type") == "Manual"

	for row in doc.items:
		item_code = row.item_code
		row_qty = flt(row.qty)

		# Evaluate replenishment schedule for item
		sched = get_effective_replenishment_schedule(
			item_code, store=store_doc.name, cluster=store_doc.cluster
		)
		is_due = is_item_due_on_date(sched.get("frequency"), sched.get("order_days"), posting_date)

		# Estimate item value (using row rate, item valuation rate, or standard price)
		item_rate = flt(row.rate or row.amount)
		if item_rate <= 0:
			item_rate = flt(
				frappe.db.get_value("Item", item_code, "valuation_rate")
				or frappe.db.get_value("Item Price", {"item_code": item_code}, "price_list_rate")
				or 100.0
			)
		item_amount = row_qty * item_rate

		if is_manual or not is_due:
			off_schedule_amount += item_amount

	# Determine if Area Manager approval is required
	if off_schedule_amount > limit:
		doc.nir_requires_area_manager_approval = 1
		if doc.nir_area_manager_approval_status != "Approved":
			doc.nir_area_manager_approval_status = "Pending Approval"
	else:
		if doc.nir_area_manager_approval_status != "Approved":
			doc.nir_requires_area_manager_approval = 0
			doc.nir_area_manager_approval_status = "Approved"


def before_submit_manual_indent(doc, method=None):
	"""Block submission of manual/off-schedule store indents exceeding set limit if not Area Manager approved."""
	if doc.material_request_type != "Material Transfer":
		return

	if doc.get("nir_requires_area_manager_approval") and doc.get("nir_area_manager_approval_status") != "Approved":
		target_wh = doc.items[0].warehouse if doc.items else ""
		store_limit = frappe.db.get_value("Pharmacy Store", {"warehouse": target_wh}, "nir_manual_indent_limit") or 5000.0

		frappe.throw(
			_("Manual store indent value exceeds limit of ₹{0}. Area Manager approval is required before submission.").format(
				flt(store_limit, 2)
			),
			title=_("Area Manager Approval Required"),
			exc=frappe.ValidationError,
		)


@frappe.whitelist()
def approve_manual_store_indent(material_request: str) -> dict:
	"""Approve a manual store indent as Area Manager or System Manager."""
	frappe.has_permission("Material Request", "write", throw=True)
	mr = frappe.get_doc("Material Request", material_request)

	user_roles = frappe.get_roles(frappe.session.user)
	if "Area Manager" not in user_roles and "System Manager" not in user_roles and "Pharmacy Management" not in user_roles:
		frappe.throw(_("Only an Area Manager or System Manager can approve manual store indents."), title=_("Permission Denied"))

	mr.nir_area_manager_approval_status = "Approved"
	mr.nir_area_manager_approved_by = frappe.session.user
	mr.nir_area_manager_approved_on = now()
	mr.save(ignore_permissions=True)

	return {"name": mr.name, "approval_status": mr.nir_area_manager_approval_status, "approved_by": mr.nir_area_manager_approved_by}
