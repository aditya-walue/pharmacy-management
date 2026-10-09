"""Online order status from ERPNext Delivery Trips.

Home delivery: a Delivery Note on a submitted Delivery Trip means the order has left: Dispatched (Partly Dispatched
while some of it has not shipped). When the trip's stop for that Delivery Note is marked Visited, the order is
Delivered. Cancelling the trip, or taking the stop off it, puts the order back to Confirmed.
Store pickup: there is no trip; submitting the Delivery Note is the hand-over, so the order is Delivered.
Before any of that: Picking (draft Pick List) and Packed (submitted Pick List), see picking.py.
"""

import frappe
from frappe import _
from frappe.utils import flt

FINAL_STATUSES = ("Cancelled", "Rejected")
BEFORE_SHIPPING = ("Cart", "Prescription Review", "Awaiting Payment")


def update_from_trip(doc, method=None):
	"""Delivery Trip submit / update after submit (stop visited) / cancel."""
	notes = [stop.delivery_note for stop in doc.delivery_stops if stop.delivery_note]
	# a stop removed after submit no longer shows on the trip, so recheck everything this trip ever carried
	notes += frappe.get_all("Delivery Note", filters={"delivery_trip": doc.name, "docstatus": 1}, pluck="name")
	for so in online_orders(set(notes)):
		refresh_status(so)


def update_from_delivery_note(doc, method=None):
	"""Delivery Note submit / cancel: a Delivery Note on its own does not dispatch the order, but changes what is left to ship."""
	for so in online_orders([doc.name]):
		refresh_status(so)


def online_orders(delivery_notes):
	if not delivery_notes:
		return []
	orders = frappe.get_all("Delivery Note Item", filters={"parent": ("in", list(delivery_notes)), "against_sales_order": ("is", "set")},
		pluck="against_sales_order", distinct=True)
	return frappe.get_all("Sales Order", filters={"name": ("in", orders or [""]), "nir_is_online_order": 1}, pluck="name")


def trip_state(delivery_note):
	"""(on a submitted trip, stop visited) for a Delivery Note."""
	stops = frappe.db.sql(
		"""select stop.visited from `tabDelivery Stop` stop join `tabDelivery Trip` trip on trip.name = stop.parent
		where stop.delivery_note = %s and trip.docstatus = 1""",
		delivery_note,
	)
	return bool(stops), any(visited for (visited,) in stops)


def refresh_status(sales_order):
	so = frappe.get_doc("Sales Order", sales_order)
	if so.nir_online_status in FINAL_STATUSES:
		return

	notes = frappe.get_all("Delivery Note Item", filters={"against_sales_order": so.name, "docstatus": 1}, pluck="parent", distinct=True)
	states = [trip_state(dn) for dn in notes]
	fully_shipped = flt(so.per_delivered) >= 100

	if so.nir_fulfilment_type == "Store Pickup":
		# no trip: the Delivery Note is the hand-over at the counter
		if not notes and so.nir_online_status in BEFORE_SHIPPING:
			return
		status = "Delivered" if fully_shipped else ("Partly Dispatched" if notes else ready_state(so.name))
	elif states and all(visited for _on_trip, visited in states) and fully_shipped:
		status = "Delivered"
	elif states and all(on_trip for on_trip, _visited in states) and fully_shipped:
		status = "Dispatched"
	elif any(on_trip for on_trip, _visited in states):
		status = "Partly Dispatched"
	elif so.nir_online_status in BEFORE_SHIPPING:
		return
	else:
		status = ready_state(so.name)

	if status == so.nir_online_status:
		return
	so.db_set("nir_online_status", status)
	so.add_comment("Info", _("Online status: {0}").format(status))
	notify_customer(so, status)


def ready_state(sales_order):
	"""Not on a trip yet: Packed / Picking from its Pick List, else Confirmed."""
	from pharmacy.online.picking import pick_state

	return pick_state(sales_order) or "Confirmed"


def notify_customer(so, status):
	if status not in ("Packed", "Dispatched", "Partly Dispatched", "Delivered"):
		return
	try:
		from pharmacy.online.order_notifications import send_order_email

		intro = {
			"Packed": _("Your order <strong>#{0}</strong> is packed and will be dispatched soon."),
			"Dispatched": _("Your order <strong>#{0}</strong> is out for delivery."),
			"Partly Dispatched": _("Part of your order <strong>#{0}</strong> is out for delivery; the rest will follow."),
			"Delivered": _("Your order <strong>#{0}</strong> has been delivered. Thank you!"),
		}[status].format(so.name)
		so.reload()
		send_order_email(so, status_label=status, message_intro=intro)
	except Exception:
		frappe.log_error(title=f"Order status email failed for {so.name}")
