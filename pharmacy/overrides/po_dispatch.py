"""Email submitted POs to the supplier and capture their acknowledgement and expected delivery date."""

import json

import frappe
from frappe import _
from frappe.core.doctype.communication.email import make
from frappe.utils import add_to_date, cint, get_url, getdate, now_datetime, today

ACK_PAGE = "/po-acknowledgement"
DEFAULT_REMINDER_HOURS = 24


def send_on_submit(doc, method=None):
	# after commit, so a mail failure can't roll back the submit
	frappe.enqueue(send_po_to_supplier, purchase_order=doc.name, enqueue_after_commit=True)


@frappe.whitelist()
def resend_po(purchase_order: str):
	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("email")
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted Purchase Orders can be sent to the supplier"))
	return send_po_to_supplier(purchase_order)


def send_po_to_supplier(purchase_order, reminder=False):
	doc = frappe.get_doc("Purchase Order", purchase_order)
	recipient = get_supplier_email(doc)
	if not recipient:
		set_email_status(doc, "Failed", _("No email address on the supplier or its contact"))
		return "Failed"

	link = get_url(f"{ACK_PAGE}?name={doc.name}")
	subject = (_("Reminder: please acknowledge Purchase Order {0}") if reminder else _("Purchase Order {0}")).format(
		doc.name
	)
	content = _(
		"<p>Dear {0},</p><p>Please find attached our Purchase Order {1} dated {2}.</p>"
		"<p>Kindly acknowledge it and confirm the expected delivery date on our supplier portal:"
		' <a href="{3}">{3}</a></p>'
	).format(doc.supplier_name or doc.supplier, doc.name, frappe.format(doc.transaction_date, "Date"), link)

	try:
		make(
			doctype=doc.doctype,
			name=doc.name,
			recipients=recipient,
			subject=subject,
			content=content,
			send_email=True,
			print_format=frappe.get_meta(doc.doctype).default_print_format or "Standard",
		)
	except frappe.OutgoingEmailError:
		set_email_status(doc, "Failed", _("Outgoing email is not set up"))
		return "Failed"

	if not reminder and doc.nir_po_email_status != "Acknowledged":
		frappe.db.set_value(
			doc.doctype, doc.name, {"nir_po_email_status": "Sent", "nir_po_sent_on": now_datetime()}
		)
	return "Sent"


def get_supplier_email(doc):
	if doc.get("contact_email"):
		return doc.contact_email

	email, contact = frappe.db.get_value("Supplier", doc.supplier, ["email_id", "supplier_primary_contact"])
	if not email and contact:
		email = frappe.db.get_value("Contact", contact, "email_id")
	return email


def set_email_status(doc, status, reason):
	frappe.db.set_value(doc.doctype, doc.name, "nir_po_email_status", status)
	doc.add_comment("Comment", _("PO not emailed to supplier: {0}").format(reason))


@frappe.whitelist()
def acknowledge_po(
	purchase_order: str,
	expected_delivery_date: str,
	confirmation_no: str | None = None,
	remarks: str | None = None,
	lines: str | None = None,
):
	"""Record the supplier's acknowledgement. `lines` is an optional JSON map of row name to delivery date."""
	doc = frappe.get_doc("Purchase Order", purchase_order)
	is_supplier = doc.supplier in get_suppliers_for_user()
	if not is_supplier:
		# buyers record acknowledgements received by phone or email
		doc.check_permission("write")

	if doc.docstatus != 1 or doc.status in ("Closed", "Completed", "Cancelled"):
		frappe.throw(_("Purchase Order {0} is not open").format(doc.name))

	header_date = validate_delivery_date(doc, expected_delivery_date)
	line_dates = json.loads(lines) if lines else {}
	for row in doc.items:
		row.expected_delivery_date = validate_delivery_date(doc, line_dates.get(row.name)) or header_date

	doc.order_confirmation_no = confirmation_no or doc.order_confirmation_no
	doc.order_confirmation_date = today()
	doc.nir_expected_delivery_date = header_date
	doc.nir_acknowledged_on = now_datetime()
	doc.nir_acknowledged_by = frappe.session.user
	doc.nir_ack_remarks = remarks
	doc.nir_po_email_status = "Acknowledged"
	doc.flags.ignore_permissions = True
	doc.save()

	doc.add_comment(
		"Comment",
		_("Acknowledged by {0}{1}. Expected delivery {2}.{3}").format(
			frappe.session.user,
			_(" (supplier)") if is_supplier else "",
			frappe.format(header_date, "Date"),
			f" {remarks}" if remarks else "",
		),
	)
	if is_supplier:
		notify_buyer(doc, _("{0} acknowledged Purchase Order {1}, delivery expected {2}").format(
			doc.supplier_name or doc.supplier, doc.name, frappe.format(header_date, "Date")
		))
	return doc.nir_po_email_status


def validate_delivery_date(doc, value):
	if not value:
		return None
	date = getdate(value)
	if date < getdate(doc.transaction_date):
		frappe.throw(_("Expected delivery date cannot be before the PO date {0}").format(
			frappe.format(doc.transaction_date, "Date")
		))
	return date


def get_suppliers_for_user(user=None):
	user = user or frappe.session.user
	if user == "Guest":
		return []
	return frappe.get_all(
		"Portal User", filters={"parenttype": "Supplier", "user": user}, pluck="parent", distinct=True
	)


def notify_buyer(doc, subject):
	frappe.get_doc(
		{
			"doctype": "Notification Log",
			"for_user": doc.owner,
			"type": "Alert",
			"document_type": doc.doctype,
			"document_name": doc.name,
			"subject": subject,
		}
	).insert(ignore_permissions=True)


def send_ack_reminders():
	"""Hourly: chase POs the supplier hasn't acknowledged within the configured hours, once."""
	hours = cint(frappe.db.get_single_value("Buying Settings", "nir_po_ack_reminder_hours")) or DEFAULT_REMINDER_HOURS
	overdue = frappe.get_all(
		"Purchase Order",
		filters={
			"docstatus": 1,
			"status": ("not in", ("Closed", "Completed", "Cancelled")),
			"nir_po_email_status": "Sent",
			"nir_ack_reminder_sent": 0,
			"nir_po_sent_on": ("<=", add_to_date(now_datetime(), hours=-hours)),
		},
		pluck="name",
	)
	for name in overdue:
		doc = frappe.get_doc("Purchase Order", name)
		notify_buyer(doc, _("{0} has not acknowledged Purchase Order {1} after {2} hours").format(
			doc.supplier_name or doc.supplier, doc.name, hours
		))
		send_po_to_supplier(name, reminder=True)
		frappe.db.set_value("Purchase Order", name, "nir_ack_reminder_sent", 1)
