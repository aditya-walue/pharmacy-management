# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Store-to-store transfers for patient needs and stock balancing, with approval and documents (ST-04)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.controlled_drugs import CONTROLLED_CATEGORIES, post
from pharmacy.overrides.inventory import enrich, get_batch_stock
from pharmacy.overrides.store_transfer import make_challan, make_invoice, needs_invoice

DEFAULT_AUTO_LIMIT = 5000
APPROVER_ROLE = "Area Manager"


class StoreTransferRequest(Document):
	def validate(self):
		if self.from_store == self.to_store:
			frappe.throw(_("Sending and receiving store must differ"))
		for store in (self.from_store, self.to_store):
			if not frappe.db.exists("Pharmacy Store", {"warehouse": store}):
				frappe.throw(_("{0} is not a Pharmacy Store warehouse").format(store))
		for row in self.items:
			bin_ = frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": self.from_store},
				["actual_qty", "valuation_rate"], as_dict=True) or frappe._dict()
			row.available_qty = flt(bin_.actual_qty)
			row.valuation_rate = flt(bin_.valuation_rate) or flt(frappe.db.get_value("Item", row.item_code, "valuation_rate"))
			row.amount = flt(row.qty) * row.valuation_rate
		self.total_value = sum(flt(r.amount) for r in self.items)


def get_request(name, statuses, perm="write"):
	doc = frappe.get_doc("Store Transfer Request", name)
	doc.check_permission(perm)
	if doc.status not in statuses:
		frappe.throw(_("{0} is {1}").format(doc.name, doc.status))
	return doc


@frappe.whitelist()
def request_approval(request: str):
	"""Patient-need requests within the limit go straight through; everything else waits for the Area Manager."""
	doc = get_request(request, ("Draft",))
	short = [f"{r.item_code} ({r.available_qty})" for r in doc.items if flt(r.qty) > flt(r.available_qty)]
	if short:
		frappe.throw(_("Not enough stock at {0}: {1}").format(doc.from_store, ", ".join(short)))

	limit = frappe.db.get_single_value("Stock Settings", "nir_patient_transfer_auto_limit")
	limit = flt(limit) if limit is not None else DEFAULT_AUTO_LIMIT
	if doc.purpose in ("Patient Need", "Online Order") and doc.total_value <= limit:
		doc.status = "Approved"
		doc.approval_remarks = _("Patient need within {0}: approved automatically").format(frappe.format(limit, "Currency"))
		doc.approved_on = now_datetime()
	else:
		doc.status = "Pending Approval"
		for user in get_users_with_role(APPROVER_ROLE):
			frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": doc.doctype,
				"document_name": doc.name, "subject": _("Approve transfer {0}: {1} → {2}").format(doc.name, doc.from_store, doc.to_store)}
			).insert(ignore_permissions=True)
	doc.save()
	return doc.status


@frappe.whitelist()
def decide(request: str, action: str, remarks: str | None = None):
	doc = get_request(request, ("Pending Approval",), perm="read")
	if APPROVER_ROLE not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only an {0} can approve transfers").format(APPROVER_ROLE), frappe.PermissionError)
	if frappe.session.user == doc.owner:
		frappe.throw(_("You raised this request, so someone else must approve it."))
	if action == "Reject" and not remarks:
		frappe.throw(_("Give a reason for rejecting"))
	doc.status = "Approved" if action == "Approve" else "Rejected"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.approval_remarks = remarks
	doc.save(ignore_permissions=True)
	return doc.status


@frappe.whitelist()
def dispatch(request: str):
	"""Sending store ships it: earliest-expiry batches, challan (same GSTIN) or tax invoice."""
	doc = get_request(request, ("Approved",))
	rows = []
	for line in doc.items:
		rows += allocate(doc.from_store, line.item_code, flt(line.qty))

	remarks = _("Store transfer {0} ({1}) to {2}").format(doc.name, doc.purpose, doc.to_store)
	if needs_invoice(doc.company, doc.from_store, doc.to_store):
		document = make_invoice(doc.company, doc.to_store, rows, remarks, nir_store_transfer=doc.name)
	else:
		document = make_challan(doc.company, doc.to_store, rows, remarks, nir_store_transfer=doc.name)

	for row in document.items:
		category = frappe.get_cached_value("Item", row.item_code, "nir_regulatory_category")
		if category in CONTROLLED_CATEGORIES:
			post(document, frappe._dict(row.as_dict(), warehouse=row.get("s_warehouse") or row.get("warehouse")),
				category, "Transfer", qty_out=flt(row.get("transfer_qty") or row.get("stock_qty")))

	doc.status = "Dispatched"
	doc.dispatch_doctype, doc.dispatch_name = document.doctype, document.name
	doc.save()
	return document.name


def allocate(store, item_code, qty):
	stock = sorted(
		[r for r in enrich(get_batch_stock(warehouses=[store], item_codes=[item_code])) if flt(r.qty) > 0],
		key=lambda r: getdate(r.expiry_date) if r.expiry_date else getdate("9999-12-31"),
	)
	rows, remaining = [], qty
	for r in stock:
		if remaining <= 0:
			break
		take = min(remaining, flt(r.qty))
		rows.append({"item_code": item_code, "qty": take, "s_warehouse": store, "batch_no": r.batch_no})
		remaining -= take
	if remaining > 0.0001:
		frappe.throw(_("Only {0} of {1} available at {2}").format(qty - remaining, item_code, store))
	return rows
