"""Stock adjustments need a reason code and a value-tiered approval by someone other than the maker (WH-04).

Adjustments are Stock Reconciliations (not opening stock) and Material Receipt / Material Issue entries.
Entries raised by an already-approved process (a Stock Count, a QA Quarantine Decision) carry that approval.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

DEFAULT_LIMIT = 10000
TIER_ROLES = ("Warehouse Manager", "Pharmacy Management")
ADJUSTING_ENTRY_TYPES = ("Material Receipt", "Material Issue")


def get_approver_role(value):
	"""Warehouse Manager up to the Stock Settings limit, Pharmacy Management above it."""
	limit = frappe.db.get_single_value("Stock Settings", "nir_adjustment_approval_limit")
	limit = flt(limit) if limit is not None else DEFAULT_LIMIT
	return TIER_ROLES[0] if abs(flt(value)) <= limit else TIER_ROLES[1]


def can_approve(role, roles=None):
	"""Pharmacy Management may approve anything Warehouse Manager can."""
	roles = set(roles or frappe.get_roles())
	return role in roles or (role == TIER_ROLES[0] and TIER_ROLES[1] in roles) or "System Manager" in roles


def is_adjustment(doc):
	if doc.doctype == "Stock Reconciliation":
		return doc.purpose != "Opening Stock"
	return doc.purpose in ADJUSTING_ENTRY_TYPES


def is_preapproved(doc):
	if doc.get("nir_stock_count"):
		return frappe.db.get_value("Stock Count", doc.nir_stock_count, "status") == "Approved"
	if doc.get("nir_transfer_discrepancy"):
		return frappe.db.get_value("Transfer Discrepancy", doc.nir_transfer_discrepancy, "status") == "Resolved"
	if doc.get("nir_quarantine_decision"):
		return frappe.db.get_value("Quarantine Decision", doc.nir_quarantine_decision, "docstatus") == 1
	return False


def get_value(doc):
	if doc.doctype == "Stock Reconciliation":
		return sum(abs((flt(r.qty) - flt(r.current_qty)) * flt(r.valuation_rate or r.current_valuation_rate)) for r in doc.items)
	return sum(abs(flt(r.basic_amount) or flt(r.amount)) for r in doc.items)


def get_signature(doc):
	lines = sorted(
		(r.item_code, r.get("batch_no") or "", r.get("warehouse") or r.get("s_warehouse") or r.get("t_warehouse") or "", flt(r.qty))
		for r in doc.items
	)
	return hashlib.sha1(json.dumps([doc.nir_reason_code, lines]).encode()).hexdigest()


def validate_adjustment(doc, method=None):
	if not is_adjustment(doc) or doc.get("is_return"):
		return

	if not doc.nir_reason_code:
		frappe.throw(_("Select a Reason Code for this stock adjustment"), title=_("Reason code required"))
	reason = frappe.db.get_value("Stock Adjustment Reason", doc.nir_reason_code, ["disabled", "applies_to"], as_dict=True)
	if not reason or reason.disabled or reason.applies_to not in ("All", doc.doctype):
		frappe.throw(_("Reason Code {0} cannot be used on a {1}").format(doc.nir_reason_code, doc.doctype))

	doc.nir_adjustment_value = get_value(doc)
	doc.nir_adjustment_approver_role = get_approver_role(doc.nir_adjustment_value)

	# any change after approval asks for approval again
	if doc.nir_adjustment_approved_by and doc.nir_adjustment_signature != get_signature(doc):
		doc.nir_adjustment_approved_by = doc.nir_adjustment_approved_on = doc.nir_adjustment_signature = None


def require_approval(doc, method=None):
	if not is_adjustment(doc) or doc.get("is_return") or is_preapproved(doc):
		return
	if not doc.nir_adjustment_approved_by:
		frappe.throw(
			_("This adjustment of {0} needs approval by a {1}").format(
				frappe.format(doc.nir_adjustment_value, "Currency"), doc.nir_adjustment_approver_role
			),
			title=_("Approval required"),
		)


@frappe.whitelist()
def approve_adjustment(doctype: str, name: str):
	if doctype not in ("Stock Entry", "Stock Reconciliation"):
		frappe.throw(_("Not a stock adjustment"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.docstatus != 0:
		frappe.throw(_("{0} is not a draft").format(name))
	if frappe.session.user == doc.owner:
		frappe.throw(_("You created this adjustment, so someone else must approve it."))
	if not can_approve(doc.nir_adjustment_approver_role):
		frappe.throw(_("Only a {0} can approve this adjustment").format(doc.nir_adjustment_approver_role), frappe.PermissionError)

	doc.nir_adjustment_approved_by = frappe.session.user
	doc.nir_adjustment_approved_on = now_datetime()
	doc.nir_adjustment_signature = get_signature(doc)
	doc.flags.ignore_permissions = True
	doc.save()
	doc.add_comment("Comment", _("Adjustment approved ({0})").format(doc.nir_reason_code))
