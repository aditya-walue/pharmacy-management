"""Order status update email notifications for Pharmacy Store customers."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money


def get_customer_email(so):
	"""Resolve recipient email from Sales Order, Customer master, Contact or User."""
	if so.get("contact_email") and "@" in so.contact_email:
		return so.contact_email.strip()

	if so.get("customer"):
		email = frappe.db.get_value("Customer", so.customer, "email_id")
		if email and "@" in email:
			return email.strip()

	if so.get("contact_person"):
		email = frappe.db.get_value("Contact", so.contact_person, "email_id")
		if email and "@" in email:
			return email.strip()

	if so.get("owner") and "@" in so.owner and so.owner not in ("Administrator", "Guest"):
		return so.owner.strip()

	return None


def send_order_email(so, status_label=None, message_intro=None):
	"""Send a branded email notification to the customer with order details."""
	recipient = get_customer_email(so)
	if not recipient:
		return False

	status = status_label or so.get("nir_online_status") or so.get("status") or "Placed"
	patient_name = so.get("nir_online_patient_name") or so.get("nir_patient_name") or so.get("customer_name") or "Customer"
	currency = so.get("currency") or "INR"

	# Build items HTML table
	rows_html = ""
	for row in so.get("items") or []:
		item_total = flt(row.qty) * flt(row.rate)
		rows_html += f"""
		<tr>
			<td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; color: #1e293b;">
				<strong>{row.item_name or row.item_code}</strong>
				<div style="font-size: 11px; color: #64748b;">Code: {row.item_code}</div>
			</td>
			<td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: center; color: #1e293b;">
				{row.qty} {row.uom or ''}
			</td>
			<td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: right; color: #1e293b;">
				{fmt_money(row.rate, currency=currency)}
			</td>
			<td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: right; font-weight: 600; color: #1e293b;">
				{fmt_money(item_total, currency=currency)}
			</td>
		</tr>
		"""

	fulfillment_info = so.get("nir_fulfilment_type") or "Delivery"
	if so.get("nir_fulfilment_type") == "Store Pickup" and so.get("nir_pickup_store"):
		fulfillment_info = f"Store Pickup at {so.nir_pickup_store}"
	elif so.get("nir_pincode"):
		fulfillment_info = f"Home Delivery (Pincode: {so.nir_pincode})"

	intro = message_intro or f"Your order <strong>#{so.name}</strong> has been updated to <strong>{status}</strong>."

	html = f"""
	<!DOCTYPE html>
	<html>
	<head><meta charset="utf-8" /></head>
	<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #0f172a;">
		<div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
			
			<!-- Header -->
			<div style="background: linear-gradient(135deg, #064e3b, #059669); color: #ffffff; padding: 24px 30px;">
				<div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; opacity: 0.9;">Pharmacy Store</div>
				<h1 style="font-size: 22px; font-weight: 800; margin: 6px 0 0 0; letter-spacing: -0.5px;">Order Status Update</h1>
			</div>

			<!-- Body -->
			<div style="padding: 28px 30px;">
				<p style="font-size: 15px; margin-top: 0; color: #334155;">Hello <strong>{patient_name}</strong>,</p>
				<p style="font-size: 14px; line-height: 1.5; color: #475569;">{intro}</p>

				<!-- Status Box -->
				<div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 14px 18px; margin: 20px 0;">
					<div style="font-size: 12px; color: #047857; text-transform: uppercase; font-weight: 700;">Current Status</div>
					<div style="font-size: 17px; font-weight: 800; color: #065f46; margin-top: 2px;">{status}</div>
					<div style="font-size: 12px; color: #065f46; margin-top: 4px;">Fulfillment: <strong>{fulfillment_info}</strong></div>
				</div>

				<!-- Items Table -->
				<h3 style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; margin: 24px 0 10px 0;">Order Details</h3>
				<table style="width: 100%; border-collapse: collapse;">
					<thead>
						<tr style="background: #f1f5f9; text-align: left; font-size: 12px; color: #475569;">
							<th style="padding: 8px 12px;">Item</th>
							<th style="padding: 8px 12px; text-align: center;">Qty</th>
							<th style="padding: 8px 12px; text-align: right;">Rate</th>
							<th style="padding: 8px 12px; text-align: right;">Amount</th>
						</tr>
					</thead>
					<tbody>
						{rows_html}
					</tbody>
				</table>

				<!-- Total -->
				<div style="margin-top: 16px; padding: 14px 12px; background: #f8fafc; border-radius: 8px; text-align: right;">
					<span style="font-size: 14px; color: #64748b; margin-right: 12px;">Grand Total:</span>
					<span style="font-size: 18px; font-weight: 800; color: #0f172a;">{fmt_money(so.grand_total, currency=currency)}</span>
				</div>

				<!-- Footer note -->
				<p style="font-size: 12px; color: #94a3b8; margin-top: 28px; line-height: 1.5; border-top: 1px solid #f1f5f9; padding-top: 16px;">
					If you have questions regarding your prescription or medication, please reply to this email or visit your nearest Pharmacy Store location.
				</p>
			</div>
		</div>
	</body>
	</html>
	"""

	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=f"[Pharmacy Store] Order #{so.name} Update: {status}",
			message=html,
			reference_doctype="Sales Order",
			reference_name=so.name,
			sender_name="Pharmacy Store",
		)
		so.add_comment("Comment", _("Order update email sent to {0} (Status: {1})").format(recipient, status))
		return True
	except Exception as e:
		frappe.log_error(f"Failed to send order email for {so.name}: {e}", "Pharmacy Order Email")
		return False


def on_sales_order_status_change(doc, method=None):
	"""Hook triggered on Sales Order update to detect status transitions."""
	if not doc.get("nir_is_online_order") and not doc.get("nir_is_patient_special_order"):
		return

	doc_before = doc.get_doc_before_save()
	if not doc_before:
		return

	prev_online = doc_before.get("nir_online_status")
	curr_online = doc.get("nir_online_status")
	prev_status = doc_before.get("status")
	curr_status = doc.get("status")

	if curr_online and prev_online != curr_online:
		send_order_email(
			doc,
			status_label=curr_online,
			message_intro=f"Your order <strong>#{doc.name}</strong> status has been updated to <strong>{curr_online}</strong>.",
		)
	elif curr_status and prev_status != curr_status and curr_status not in ("Draft",):
		send_order_email(
			doc,
			status_label=curr_status,
			message_intro=f"Your order <strong>#{doc.name}</strong> status has been updated to <strong>{curr_status}</strong>.",
		)
