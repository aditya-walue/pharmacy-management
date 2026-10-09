"""Delivery Riders see only the submitted Delivery Trips they drive, and the Delivery Notes on them.

A rider is linked to a trip through the Driver record (Driver → User). Users with any wider delivery or
stock role see everything as before.
"""

import frappe
from frappe import _

RIDER_ROLE = "Delivery Rider"
WIDER_ROLES = {"System Manager", "Stock User", "Stock Manager", "Delivery User", "Delivery Manager", "Fulfillment User",
	"Dispatch Coordinator", "Warehouse Manager", "Sales User", "Accounts User"}

RIDER_PERMISSIONS = {
	# doctype: rights beyond read
	# submit: ERPNext checks it for "update after submit", i.e. ticking a stop Visited on a submitted trip
	"Delivery Trip": ("write", "submit", "print"),
	"Delivery Note": ("print",),
	"Address": (),
	"Contact": (),
	"Customer": (),
	"Driver": (),
}


def is_rider_only(user=None):
	roles = set(frappe.get_roles(user or frappe.session.user))
	return RIDER_ROLE in roles and not roles & WIDER_ROLES


def rider_drivers(user):
	return frappe.get_all("Driver", filters={"user": user}, pluck="name")


def trip_conditions(user=None):
	user = user or frappe.session.user
	if not is_rider_only(user):
		return ""
	drivers = rider_drivers(user)
	if not drivers:
		return "1=0"
	names = ", ".join(frappe.db.escape(d) for d in drivers)
	return f"`tabDelivery Trip`.docstatus = 1 and `tabDelivery Trip`.driver in ({names})"


def delivery_note_conditions(user=None):
	user = user or frappe.session.user
	if not is_rider_only(user):
		return ""
	drivers = rider_drivers(user)
	if not drivers:
		return "1=0"
	names = ", ".join(frappe.db.escape(d) for d in drivers)
	return f"""`tabDelivery Note`.name in (select stop.delivery_note from `tabDelivery Stop` stop
		join `tabDelivery Trip` trip on trip.name = stop.parent where trip.docstatus = 1 and trip.driver in ({names}))"""


def has_trip_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not is_rider_only(user):
		return None
	if doc.docstatus != 1 or doc.driver not in rider_drivers(user):
		return False
	# riders only update stops on submitted trips (Visited); drafts are hidden, so "submit" here can only be an
	# update after submit; they never create or cancel trips
	return ptype in (None, "read", "write", "submit", "print", "email", "report")


def has_delivery_note_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not is_rider_only(user):
		return None
	if ptype not in (None, "read", "print"):
		return False
	drivers = rider_drivers(user)
	return bool(drivers) and bool(frappe.db.sql(
		"""select 1 from `tabDelivery Stop` stop join `tabDelivery Trip` trip on trip.name = stop.parent
		where stop.delivery_note = %s and trip.docstatus = 1 and trip.driver in %s limit 1""",
		(doc.name, tuple(drivers)),
	))


def setup_rider_permissions():
	"""Role permissions for Delivery Rider (Custom DocPerm), idempotent."""
	from frappe.permissions import add_permission, update_permission_property

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	# show the Visited tick in the trip's stop table
	make_property_setter("Delivery Stop", "visited", "in_list_view", 1, "Check", validate_fields_for_doctype=False)
	make_property_setter("Delivery Stop", "visited", "columns", 1, "Int", validate_fields_for_doctype=False)
	if not frappe.db.exists("Role", RIDER_ROLE):
		return
	for doctype, rights in RIDER_PERMISSIONS.items():
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": RIDER_ROLE, "permlevel": 0}):
			add_permission(doctype, RIDER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, RIDER_ROLE, 0, right, 1, validate=False)


def validate_rider_update(doc, method=None):
	"""A rider may tick stops Visited but not change the trip's vehicle, driver or stops."""
	if not is_rider_only() or doc.is_new():
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	for field in ("driver", "vehicle", "departure_time", "company"):
		if before.get(field) != doc.get(field):
			frappe.throw(_("Riders can only mark stops as visited"))
	if [s.delivery_note for s in before.delivery_stops] != [s.delivery_note for s in doc.delivery_stops]:
		frappe.throw(_("Riders can only mark stops as visited"))
