"""Delivery Trip stops take the customer and delivery address from their Delivery Note, or the customer's saved address."""

import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display


def fill_stops(doc, method=None):
	"""before_validate: runs before the stop's mandatory Address check."""
	for stop in doc.delivery_stops:
		if stop.address and stop.customer:
			continue
		details = stop_details(stop.delivery_note, stop.customer)
		stop.customer = stop.customer or details.get("customer")
		if not stop.address and details.get("address"):
			stop.address = details["address"]
			stop.customer_address = details["address_display"]
		if not stop.contact and details.get("contact"):
			stop.contact = details["contact"]
		if not stop.address:
			frappe.throw(_("Row #{0}: {1} has no delivery address. Add one to the customer or set Shipping Address on Delivery Note {2}.").format(
				stop.idx, stop.customer or _("this stop"), stop.delivery_note or ""), title=_("Address missing"))


@frappe.whitelist()
def get_stop_details(delivery_note: str | None = None, customer: str | None = None):
	frappe.has_permission("Delivery Trip", "write", throw=True)
	return stop_details(delivery_note, customer)


def stop_details(delivery_note=None, customer=None):
	address = contact = None
	if delivery_note:
		dn = frappe.db.get_value("Delivery Note", delivery_note,
			["customer", "shipping_address_name", "customer_address", "contact_person"], as_dict=True) or frappe._dict()
		customer = customer or dn.customer
		address = dn.shipping_address_name or dn.customer_address
		contact = dn.contact_person
	if customer and not address:
		address = customer_address(customer)
	return {
		"customer": customer,
		"address": address,
		"address_display": get_address_display(address) if address else None,
		"contact": contact,
	}


def customer_address(customer):
	"""Shipping address first, then the primary one, then any enabled address of the customer."""
	rows = frappe.db.sql(
		"""select addr.name from `tabAddress` addr
		join `tabDynamic Link` link on link.parent = addr.name and link.parenttype = 'Address'
		where link.link_doctype = 'Customer' and link.link_name = %s and addr.disabled = 0
		order by addr.is_shipping_address desc, addr.is_primary_address desc, addr.modified desc
		limit 1""",
		customer,
	)
	return rows[0][0] if rows else frappe.db.get_value("Customer", customer, "customer_primary_address")


@frappe.whitelist()
def mark_stop_delivered(delivery_trip: str, stop: str):
	"""Rider / dispatcher button: tick the stop Visited, which makes the online order Delivered."""
	trip = frappe.get_doc("Delivery Trip", delivery_trip)
	trip.check_permission("write")
	if trip.docstatus != 1:
		frappe.throw(_("Submit the trip before marking deliveries"))
	row = next((s for s in trip.delivery_stops if s.name == stop), None)
	if not row:
		frappe.throw(_("Stop not found on this trip"))
	if row.visited:
		return trip.status
	row.visited = 1
	trip.save()
	return frappe.db.get_value("Delivery Trip", trip.name, "status")
