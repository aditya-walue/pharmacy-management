# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Store ↔ warehouse discrepancy workflow (ST-03): store reports, DC investigates, approver signs off, stock adjusted."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.stock_adjustment import can_approve, get_approver_role

# what each DC finding means for stock, per discrepancy type
ALLOWED = {
	"Short": ("Found at DC", "Transit Loss", "Not Accepted"),
	"Excess": ("Excess Confirmed", "Not Accepted"),
	"Damaged": ("Damaged Write-off", "Not Accepted"),
}


class TransferDiscrepancy(Document):
	def validate(self):
		for row in self.items:
			if row.finding and row.finding not in ALLOWED[row.discrepancy_type]:
				frappe.throw(_("Row #{0}: {1} is not a finding for a {2} line").format(row.idx, row.finding, row.discrepancy_type))


def get_doc_for(name, statuses):
	doc = frappe.get_doc("Transfer Discrepancy", name)
	doc.check_permission("read")
	if doc.status not in statuses:
		frappe.throw(_("{0} is {1}").format(doc.name, doc.status))
	return doc


@frappe.whitelist()
def start_investigation(discrepancy: str):
	if "Warehouse Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
		frappe.throw(_("The warehouse investigates discrepancies"), frappe.PermissionError)
	doc = get_doc_for(discrepancy, ("Open",))
	doc.status = "Under Investigation"
	doc.investigated_by = frappe.session.user
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def submit_findings(discrepancy: str):
	doc = get_doc_for(discrepancy, ("Under Investigation",))
	if frappe.session.user != doc.investigated_by and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only the investigator can submit findings"))
	missing = [f"#{r.idx}" for r in doc.items if not r.finding]
	if missing:
		frappe.throw(_("Record a finding for every line: {0}").format(", ".join(missing)))
	doc.status = "Pending Approval"
	doc.approver_role = get_approver_role(doc.total_value)
	doc.save(ignore_permissions=True)
	for user in get_users_with_role(doc.approver_role):
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": doc.doctype,
			"document_name": doc.name, "subject": _("Approve discrepancy findings {0} ({1})").format(doc.name, doc.store_warehouse)}
		).insert(ignore_permissions=True)


@frappe.whitelist()
def decide(discrepancy: str, action: str, remarks: str | None = None):
	doc = get_doc_for(discrepancy, ("Pending Approval",))
	if frappe.session.user in (doc.investigated_by, doc.owner):
		frappe.throw(_("The investigator or reporter cannot approve the findings"))
	if not can_approve(doc.approver_role):
		frappe.throw(_("Only a {0} can approve these findings").format(doc.approver_role), frappe.PermissionError)

	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.approval_remarks = remarks
	if action == "Reject":
		# back to the warehouse to look again
		doc.status = "Under Investigation"
		doc.save(ignore_permissions=True)
		return doc.status

	doc.status = "Resolved"
	doc.save(ignore_permissions=True)
	for row in doc.items:
		entry = make_adjustment(doc, row)
		if entry:
			frappe.db.set_value("Transfer Discrepancy Item", row.name, "adjustment", entry)
	for user in get_users_with_role("Store Pharmacist"):
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": doc.doctype,
			"document_name": doc.name, "subject": _("Discrepancy {0} for {1} resolved").format(doc.name, doc.store_warehouse)}
		).insert(ignore_permissions=True)
	return doc.status


def make_adjustment(doc, row):
	held_at = stock_location(doc)  # where the dispatched-but-missing stock sits in the books
	qty = flt(row.qty)
	moves = {
		("Short", "Found at DC"): ("Material Transfer", held_at, row.source_warehouse, None),
		("Short", "Transit Loss"): ("Material Issue", held_at, None, "Theft / Loss"),
		("Short", "Not Accepted"): ("Material Transfer", held_at, doc.store_warehouse, None) if held_at != doc.store_warehouse else None,
		("Excess", "Excess Confirmed"): ("Material Transfer", row.source_warehouse, doc.store_warehouse, None),
		("Damaged", "Damaged Write-off"): ("Material Issue", doc.store_warehouse, None, "Damage"),
	}
	move = moves.get((row.discrepancy_type, row.finding))
	if not move:
		return None
	purpose, source, target, reason = move
	entry = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": purpose,
		"company": doc.company,
		"nir_transfer_discrepancy": doc.name,
		"nir_reason_code": reason,
		"remarks": _("{0}: {1} {2}").format(doc.name, row.discrepancy_type, row.finding),
		"items": [{"item_code": row.item_code, "qty": qty, "s_warehouse": source, "t_warehouse": target,
			"batch_no": row.batch_no, "use_serial_batch_fields": 1 if row.batch_no else 0}],
	})
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry.name


def stock_location(doc):
	"""A challan's undelivered stock is still in transit; an invoice moved it into the store's books on submit."""
	if doc.dispatch_doctype == "Stock Entry":
		return frappe.db.get_value("Stock Entry Detail", {"parent": doc.dispatch_name}, "t_warehouse")
	return doc.store_warehouse
