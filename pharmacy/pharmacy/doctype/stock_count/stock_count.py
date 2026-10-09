# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Cycle counts by ABC class and full physical verification, counted blind, variances approved (WH-03).

System qty and variance sit at permission level 1, so counters never see them.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, now_datetime

from pharmacy.overrides.inventory import get_batch_stock
from pharmacy.overrides.stock_adjustment import can_approve, get_approver_role

DEFAULT_CYCLE_DAYS = {"A": 30, "B": 90, "C": 180}
COUNT_REASON = "Count Variance"


class StockCount(Document):
	def validate(self):
		self.total_lines = len(self.items)
		self.counted_lines = sum(1 for row in self.items if row.counted)
		if self.docstatus == 0:
			self.status = "Counting" if self.counted_lines else "Draft"

	@frappe.whitelist()
	def get_lines(self):
		self.check_permission("write")
		if self.docstatus != 0:
			frappe.throw(_("Lines can be fetched only on a draft count"))

		bins = get_bins(self.warehouse)
		rows = get_batch_stock(company=self.company, warehouses=bins)
		if self.count_type == "Cycle Count":
			due = get_due_items({r.item_code for r in rows}, self.abc_class, self.count_date, self.name)
			rows = [r for r in rows if r.item_code in due]

		self.items = []
		for r in sorted(rows, key=lambda r: (r.warehouse, r.item_code, r.batch_no or "")):
			self.append(
				"items",
				{
					"warehouse": r.warehouse,
					"item_code": r.item_code,
					"batch_no": r.batch_no,
					"system_qty": flt(r.qty),
					"valuation_rate": flt(r.value) / flt(r.qty) if flt(r.qty) else 0,
				},
			)
		# system qty is above the counter's permission level; without this save would blank it
		self.flags.ignore_permissions = True
		self.save()
		return len(self.items)

	def before_submit(self):
		# counters submit, but the variance fields they can't see must still be written
		self.flags.ignore_permissions = True
		uncounted = [f"#{row.idx}" for row in self.items if not row.counted]
		if uncounted:
			frappe.throw(_("Count every line before submitting ({0} not counted)").format(len(uncounted)))

		# stock may have moved while counting, so variance is against the position at submit
		current = {
			(r.warehouse, r.item_code, r.batch_no or None): r
			for r in get_batch_stock(company=self.company, warehouses={row.warehouse for row in self.items})
		}
		for row in self.items:
			position = current.get((row.warehouse, row.item_code, row.batch_no or None))
			row.system_qty = flt(position.qty) if position else 0
			if position and flt(position.qty):
				row.valuation_rate = flt(position.value) / flt(position.qty)
			row.variance_qty = flt(row.counted_qty) - flt(row.system_qty)
			row.variance_value = row.variance_qty * flt(row.valuation_rate)

		variances = [row for row in self.items if abs(flt(row.variance_qty)) > 0.0001]
		self.variance_lines = len(variances)
		self.variance_value = sum(flt(row.variance_value) for row in variances)
		self.approver_role = get_approver_role(sum(abs(flt(row.variance_value)) for row in variances)) if variances else None
		self.status = "Pending Approval" if variances else "Approved"


@frappe.whitelist()
def record_count(stock_count: str, bin_code: str, code: str, qty: float):
	"""Handheld blind count: scan the bin, scan the batch (or item), enter the qty counted."""
	doc = frappe.get_doc("Stock Count", stock_count)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted").format(doc.name))

	bin_code, code = (bin_code or "").strip(), (code or "").strip()
	if not frappe.db.exists("Warehouse", {"name": bin_code, "is_group": 0}):
		frappe.throw(_("{0} is not a bin").format(bin_code))

	batch_item = frappe.db.get_value("Batch", code, "item")
	item_code = batch_item or frappe.db.get_value("Item Barcode", {"barcode": code}, "parent") or code
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("{0} is not a known batch or item").format(code))
	batch_no = code if batch_item else None

	row = next(
		(r for r in doc.items if r.warehouse == bin_code and r.item_code == item_code and (r.batch_no or None) == batch_no),
		None,
	)
	if not row:
		# found stock the system doesn't know about here
		row = doc.append("items", {"warehouse": bin_code, "item_code": item_code, "batch_no": batch_no, "system_qty": 0})
	row.counted_qty = flt(qty)
	row.counted = 1
	row.counted_by = frappe.session.user
	doc.flags.ignore_permissions = True
	doc.save()
	return {"idx": row.idx, "item_code": item_code, "batch_no": batch_no, "counted": doc.counted_lines, "total": doc.total_lines}


@frappe.whitelist()
def act_on_count(stock_count: str, action: str, remarks: str | None = None):
	"""Approve (posting a Stock Reconciliation for the variances) or reject a submitted count."""
	doc = frappe.get_doc("Stock Count", stock_count)
	if doc.docstatus != 1 or doc.status != "Pending Approval":
		frappe.throw(_("{0} is not waiting for approval").format(doc.name))

	counters = {row.counted_by for row in doc.items} | {doc.owner}
	if frappe.session.user in counters:
		frappe.throw(_("You took part in this count, so someone else must approve it."))
	if not can_approve(doc.approver_role):
		frappe.throw(_("Only a {0} can approve this count").format(doc.approver_role), frappe.PermissionError)
	if action == "Reject" and not remarks:
		frappe.throw(_("Give a reason for rejecting"))

	values = {"approved_by": frappe.session.user, "approved_on": now_datetime(), "approval_remarks": remarks}
	if action == "Approve":
		values["status"] = "Approved"
		doc.db_set(values)
		doc.db_set("stock_reconciliation", make_reconciliation(doc))
	else:
		values["status"] = "Rejected"
		doc.db_set(values)
	doc.add_comment("Comment", _("Count {0}{1}").format(values["status"].lower(), f": {remarks}" if remarks else ""))
	return values["status"]


def make_reconciliation(doc):
	ensure_reason()
	reco = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"company": doc.company,
			"purpose": "Stock Reconciliation",
			"posting_date": doc.count_date,
			"set_posting_time": 1,
			"nir_reason_code": COUNT_REASON,
			"nir_stock_count": doc.name,
			"items": [
				{
					"item_code": row.item_code,
					"warehouse": row.warehouse,
					"batch_no": row.batch_no,
					"use_serial_batch_fields": 1 if row.batch_no else 0,
					"qty": flt(row.counted_qty),
					"valuation_rate": flt(row.valuation_rate),
				}
				for row in doc.items
				if abs(flt(row.variance_qty)) > 0.0001
			],
		}
	)
	reco.flags.ignore_permissions = True
	reco.insert()
	reco.submit()
	return reco.name


def ensure_reason():
	if not frappe.db.exists("Stock Adjustment Reason", COUNT_REASON):
		frappe.get_doc({"doctype": "Stock Adjustment Reason", "reason": COUNT_REASON, "applies_to": "Stock Reconciliation"}).insert(
			ignore_permissions=True
		)


def get_bins(warehouse):
	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	return frappe.get_all(
		"Warehouse", filters={"lft": (">=", lft), "rgt": ("<=", rgt), "is_group": 0, "disabled": 0}, pluck="name"
	)


def get_due_items(item_codes, abc_class, count_date, current):
	"""Items of the class whose last approved count is older than the class's cycle."""
	if not item_codes:
		return set()
	filters = {"name": ("in", list(item_codes))}
	if abc_class:
		filters["nir_abc_class"] = abc_class
	classes = dict(frappe.get_all("Item", filters=filters, fields=["name", "nir_abc_class"], as_list=True))

	last_counted = dict(
		frappe.db.sql(
			"""select sci.item_code, max(sc.count_date) from `tabStock Count Item` sci
			join `tabStock Count` sc on sc.name = sci.parent
			where sc.docstatus = 1 and sc.status = 'Approved' and sc.name != %s and sci.item_code in %s
			group by sci.item_code""",
			(current or "", tuple(classes) or ("",)),
		)
	)
	cycle_days = {
		cls: cint(frappe.db.get_single_value("Stock Settings", f"nir_abc_cycle_days_{cls.lower()}")) or days
		for cls, days in DEFAULT_CYCLE_DAYS.items()
	}
	due = set()
	for item, cls in classes.items():
		days = cycle_days[cls or "B"]
		last = last_counted.get(item)
		if not last or last <= add_days(count_date, -days):
			due.add(item)
	return due
