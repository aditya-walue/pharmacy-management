"""Three-way match of PO, GRN and supplier invoice; over-billing raises draft debit notes.

Quantities and rates are compared per stock unit in company currency, so invoices in a different
UOM or currency from the PO still match. Rates are net of discounts and before tax.
"""

import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import make_debit_note
from frappe import _
from frappe.utils import flt
from frappe.utils.user import get_users_with_role

ACCOUNTS_ROLE = "Pharmacy Accounts"
DEFAULT_RATE_TOLERANCE = 0.01


def validate_match(doc, method=None):
	"""before_submit: require a GRN for stock lines, then record each line's PO rate and GRN qty differences."""
	if doc.is_return:
		return

	if not doc.update_stock:
		require_grn(doc)

	rate_tolerance, qty_tolerance = get_tolerances()
	statuses = set()
	for row in doc.items:
		match_line(doc, row, rate_tolerance, qty_tolerance)
		statuses.add(row.nir_line_match)

	if statuses & {"Over-billed Qty", "Over-billed Rate", "Over-billed Qty and Rate"}:
		doc.nir_match_status = "Debit Note Raised"
	elif "Under-billed" in statuses:
		doc.nir_match_status = "Under-billed"
	else:
		doc.nir_match_status = "Matched"


def require_grn(doc):
	stock_items = set(
		frappe.get_all(
			"Item",
			filters={"name": ("in", [row.item_code for row in doc.items]), "is_stock_item": 1},
			pluck="name",
		)
	)
	missing = [
		f"#{row.idx} {row.item_code}" for row in doc.items if row.item_code in stock_items and not row.pr_detail
	]
	if missing:
		frappe.throw(
			_("Link these lines to a Purchase Receipt before submitting the invoice: {0}").format(", ".join(missing)),
			title=_("GRN required for three-way match"),
		)


def get_tolerances():
	rate = frappe.db.get_single_value("Buying Settings", "nir_match_rate_tolerance")
	qty = frappe.db.get_single_value("Buying Settings", "nir_match_qty_tolerance")
	return (flt(rate) if rate is not None else DEFAULT_RATE_TOLERANCE), flt(qty)


def match_line(doc, row, rate_tolerance, qty_tolerance):
	conversion = flt(row.conversion_factor) or 1
	billed_qty = flt(row.stock_qty) or flt(row.qty) * conversion
	billed_rate = flt(row.base_net_rate) / conversion

	row.nir_po_rate = row.nir_rate_difference = row.nir_grn_qty = row.nir_qty_difference = None
	over_rate = over_qty = under = False

	if row.po_detail:
		po_rate, po_conversion = frappe.db.get_value(
			"Purchase Order Item", row.po_detail, ["base_net_rate", "conversion_factor"]
		)
		row.nir_po_rate = flt(po_rate) / (flt(po_conversion) or 1)
		row.nir_rate_difference = billed_rate - row.nir_po_rate
		over_rate = row.nir_rate_difference > rate_tolerance
		under = row.nir_rate_difference < -rate_tolerance

	# an update-stock invoice is its own receipt, so only its rate is matched
	if row.pr_detail and not doc.update_stock:
		row.nir_grn_qty = get_unbilled_grn_qty(row.pr_detail, doc.name)
		row.nir_qty_difference = billed_qty - row.nir_grn_qty
		over_qty = row.nir_qty_difference > qty_tolerance
		under = under or row.nir_qty_difference < -qty_tolerance

	if over_qty and over_rate:
		row.nir_line_match = "Over-billed Qty and Rate"
	elif over_qty:
		row.nir_line_match = "Over-billed Qty"
	elif over_rate:
		row.nir_line_match = "Over-billed Rate"
	elif under:
		row.nir_line_match = "Under-billed"
	elif row.po_detail or row.pr_detail:
		row.nir_line_match = "Matched"
	else:
		row.nir_line_match = "Not Linked"


def get_unbilled_grn_qty(pr_detail, current_invoice):
	"""Accepted GRN stock qty net of purchase returns, less what other invoices have billed against it.

	Rate-difference debit notes are left out: they don't reduce what was billed.
	"""
	accepted = flt(frappe.db.get_value("Purchase Receipt Item", pr_detail, "stock_qty"))
	returned = flt(
		frappe.db.sql(
			"""select sum(pri.stock_qty) from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pri.purchase_receipt_item = %s and pr.docstatus = 1 and pr.is_return = 1""",
			pr_detail,
		)[0][0]
	)
	billed = flt(
		frappe.db.sql(
			"""select sum(pii.stock_qty) from `tabPurchase Invoice Item` pii
			join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pii.pr_detail = %s and pi.docstatus = 1 and pi.name != %s
			and (pi.is_return = 0 or pi.update_billed_amount_in_purchase_receipt = 1)""",
			(pr_detail, current_invoice),
		)[0][0]
	)
	return accepted + returned - billed


def raise_debit_notes(doc, method=None):
	"""on_submit: draft debit notes for over-billed qty and over-billed rate, for Accounts to review."""
	if doc.is_return or doc.nir_match_status != "Debit Note Raised":
		return

	qty_lines = {row.name: flt(row.nir_qty_difference) for row in doc.items if "Qty" in (row.nir_line_match or "")}
	rate_lines = {row.name: row for row in doc.items if "Rate" in (row.nir_line_match or "")}

	notes = []
	if qty_lines:
		notes.append(("Qty Difference", lambda: build_qty_note(doc, qty_lines)))
	if rate_lines:
		notes.append(("Rate Difference", lambda: build_rate_note(doc, rate_lines, qty_lines)))

	created = []
	for kind, builder in notes:
		# a debit note that fails validation must not undo the supplier invoice
		frappe.db.savepoint("nir_debit_note")
		try:
			note = builder()
			note.insert(ignore_permissions=True)
			created.append(note.name)
		except Exception:
			frappe.db.rollback(save_point="nir_debit_note")
			frappe.log_error(
				title=_("{0} debit note failed for {1}").format(kind, doc.name),
				reference_doctype=doc.doctype,
				reference_name=doc.name,
			)
			doc.add_comment(
				"Comment", _("Could not create the {0} debit note; raise it manually. See Error Log.").format(kind.lower())
			)

	if created:
		doc.db_set("nir_debit_notes", ", ".join(created))
		notify_accounts(doc, created)


def new_debit_note(doc, kind, update_billed):
	note = make_debit_note(doc.name)
	note.nir_debit_note_type = kind
	note.bill_no = note.bill_date = None
	note.update_billed_amount_in_purchase_receipt = update_billed
	note.update_billed_amount_in_purchase_order = update_billed
	note.remarks = _("{0} against {1} (three-way match with PO and GRN)").format(kind, doc.name)
	return note


def build_qty_note(doc, qty_lines):
	"""Return the over-billed units at the invoiced rate; billed qty on PO and GRN drops accordingly."""
	note = new_debit_note(doc, "Qty Difference", update_billed=1)
	conversions = {row.name: flt(row.conversion_factor) or 1 for row in doc.items}
	note.items = [row for row in note.items if row.purchase_invoice_item in qty_lines]
	for row in note.items:
		row.qty = -qty_lines[row.purchase_invoice_item] / conversions[row.purchase_invoice_item]
	return note


def build_rate_note(doc, rate_lines, qty_lines):
	"""Credit (invoiced − PO rate) on the units actually received; billed qty on PO and GRN is untouched."""
	note = new_debit_note(doc, "Rate Difference", update_billed=0)
	note.items = [row for row in note.items if row.purchase_invoice_item in rate_lines]
	for row in note.items:
		source = rate_lines[row.purchase_invoice_item]
		conversion = flt(source.conversion_factor) or 1
		received_qty = flt(source.qty) - max(qty_lines.get(row.purchase_invoice_item, 0), 0) / conversion
		# rate difference is per stock unit in company currency; the note is in the invoice's UOM and currency
		rate = flt(source.nir_rate_difference) * conversion / (flt(doc.conversion_rate) or 1)
		row.qty = -received_qty
		row.price_list_rate = row.rate = rate
		row.discount_percentage = row.discount_amount = row.margin_rate_or_amount = 0
	return note


def notify_accounts(doc, notes):
	subject = _("Debit notes {0} drafted for {1} ({2}); review and submit").format(
		", ".join(notes), doc.name, doc.supplier_name or doc.supplier
	)
	for user in get_users_with_role(ACCOUNTS_ROLE):
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"subject": subject,
			}
		).insert(ignore_permissions=True)
