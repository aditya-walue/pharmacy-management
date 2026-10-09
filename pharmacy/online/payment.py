"""Online payment through Razorpay (UPI, cards, net banking, wallets) using ERPNext Payment Requests on the Sales Order."""

import frappe
from frappe import _
from frappe.utils import cint

from pharmacy.online import get_settings
from pharmacy.online.cart import get_order, website_api


def create_payment_request(so):
	from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request

	settings = get_settings()
	if not settings.payment_gateway_account:
		frappe.throw(_("Set the Payment Gateway Account in Online Order Settings"))
	# a website customer has no desk rights on Payment Request; the request is made on their order's behalf
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		pr = make_payment_request(dt="Sales Order", dn=so.name, payment_gateway_account=settings.payment_gateway_account,
			loyalty_points=cint(so.loyalty_points) or None, submit_doc=1, mute_email=1, return_doc=1,
			party_type="Customer", party=so.customer, recipient_id=frappe.db.get_value("User", so.nir_website_user, "email"))
	finally:
		frappe.set_user(user)
	so.db_set("nir_payment_request", pr.name)
	return pr


@website_api
def get_payment_url(sales_order: str):
	"""Razorpay checkout link for an order awaiting payment."""
	so = get_order(sales_order, ("Awaiting Payment",))
	pr = frappe.get_doc("Payment Request", so.nir_payment_request) if so.nir_payment_request else create_payment_request(so)
	if pr.status == "Paid":
		frappe.throw(_("This order is already paid"))
	return pr.payment_url or pr.get_payment_url()


def on_payment_authorized(doc, method=None, status=None):
	"""Payment Request hook called by the gateway: post the Payment Entry against the order and confirm it."""
	if status not in ("Authorized", "Completed", "Verified") or doc.status == "Paid":
		return
	if doc.reference_doctype != "Sales Order" or not frappe.db.get_value("Sales Order", doc.reference_name, "nir_is_online_order"):
		return
	doc.flags.ignore_permissions = True
	doc.set_as_paid()
	from pharmacy.online.fulfilment import on_payment_received

	on_payment_received(doc.reference_name)
	return get_settings().payment_success_path
