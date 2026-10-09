"""Returnable totes, crates and ice boxes: issued to stores, returned, missing (custody by store)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime
from frappe.utils.user import get_users_with_role

DEFAULT_RETURN_DAYS = 7
TRACKING_ROLES = ("Dispatch Coordinator", "Warehouse Manager")


def log_movement(tote, event, store=None, trip=None, condition=None, remarks=None):
	frappe.get_doc(
		{
			"doctype": "Tote Movement",
			"tote": tote,
			"tote_type": frappe.db.get_value("Tote", tote, "tote_type"),
			"event": event,
			"store_warehouse": store,
			"dispatch_trip": trip,
			"condition": condition,
			"posted_on": now_datetime(),
			"posted_by": frappe.session.user,
			"remarks": remarks,
		}
	).insert(ignore_permissions=True)


def reset_for_reuse(tote):
	frappe.db.set_value(
		"Tote",
		tote,
		{
			"status": "Available", "holder_store": None, "issued_on": None, "current_wave": None, "store_warehouse": None,
			"seal_no": None, "sealed_by": None, "sealed_on": None, "ice_packs": 0, "packed_temperature": None,
			"dispatch_doctype": None, "dispatch_name": None,
		},
	)


@frappe.whitelist()
def mark_missing(tote: str, remarks: str):
	frappe.has_permission("Tote", "write", throw=True)
	t = frappe.db.get_value("Tote", tote, ["status", "holder_store", "last_trip"], as_dict=True)
	if t.status not in ("At Store", "In Transit", "Dispatched"):
		frappe.throw(_("Only a tote out with a store or on a trip can be marked missing"))
	frappe.db.set_value("Tote", tote, "status", "Missing")
	log_movement(tote, "Missing", store=t.holder_store, trip=t.last_trip, remarks=remarks)


@frappe.whitelist()
def mark_found(tote: str, remarks: str | None = None):
	frappe.has_permission("Tote", "write", throw=True)
	t = frappe.db.get_value("Tote", tote, ["status", "holder_store"], as_dict=True)
	if t.status != "Missing":
		frappe.throw(_("Tote {0} is not missing").format(tote))
	log_movement(tote, "Found", store=t.holder_store, remarks=remarks)
	reset_for_reuse(tote)


def alert_overdue_totes():
	"""Daily: totes held by a store longer than the return period."""
	days = cint(frappe.db.get_single_value("Stock Settings", "nir_tote_return_days")) or DEFAULT_RETURN_DAYS
	overdue = frappe.get_all(
		"Tote",
		filters={"status": "At Store", "issued_on": ("<", add_days(now_datetime(), -days))},
		fields=["name", "holder_store"],
	)
	if not overdue:
		return
	by_store = {}
	for t in overdue:
		by_store.setdefault(t.holder_store, []).append(t.name)
	subject = _("{0} totes not returned within {1} days: {2}").format(
		len(overdue), days, "; ".join(f"{store} ({len(totes)})" for store, totes in by_store.items())
	)
	for user in {u for role in TRACKING_ROLES for u in get_users_with_role(role)}:
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Report",
			 "document_name": "Tote Balance by Store", "subject": subject[:140]}
		).insert(ignore_permissions=True)
