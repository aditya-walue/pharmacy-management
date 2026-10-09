"""Partial supplies, short-closing, backorder follow-up, and supplier fill rate / lead time."""

import frappe
from erpnext.buying.doctype.purchase_order import purchase_order as erpnext_po
from frappe import _
from frappe.core.doctype.communication.email import make
from frappe.utils import add_days, cint, date_diff, flt, get_url, getdate, now_datetime, today

from pharmacy.overrides.po_dispatch import ACK_PAGE, get_supplier_email, notify_buyer

SHORT_CLOSE_REASONS = (
	"Supplier cannot supply",
	"Product discontinued",
	"Price changed",
	"Bought substitute",
	"Other",
)
OPEN_STATUSES = ("To Receive", "To Receive and Bill")
# POs whose supply is final, so their fill rate is no longer moving
FINAL_STATUSES = ("Completed", "To Bill", "Closed")
DEFAULT_FOLLOWUP_DAYS = 3
PERFORMANCE_WINDOW_DAYS = 90


# Short-closing


@frappe.whitelist()
def short_close(purchase_order: str, reason: str, remarks: str | None = None):
	"""Close a PO whose remaining qty will not be supplied, recording why."""
	if reason not in SHORT_CLOSE_REASONS:
		frappe.throw(_("Choose a short-close reason"))
	if reason == "Other" and not remarks:
		frappe.throw(_("Describe the reason in Remarks"))

	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("write")
	if po.status not in OPEN_STATUSES:
		frappe.throw(_("Only Purchase Orders still awaiting goods can be short-closed"))

	po.db_set(
		{
			"nir_short_close_reason": reason,
			"nir_short_close_remarks": remarks,
			"nir_short_closed_by": frappe.session.user,
			"nir_short_closed_on": now_datetime(),
		}
	)
	erpnext_po.update_status("Closed", purchase_order)
	update_fulfilment(purchase_order)
	po.add_comment("Comment", _("Short-closed: {0}{1}").format(reason, f". {remarks}" if remarks else ""))


@frappe.whitelist()
def update_status(status: str, name: str):
	"""Override of ERPNext's PO close/re-open: closing with qty pending must go through short_close."""
	if status == "Closed":
		ensure_short_close_reason([name])
	elif status == "Submitted":
		clear_short_close(name)
	return erpnext_po.update_status(status, name)


@frappe.whitelist()
def close_or_unclose_purchase_orders(names: str, status: str):
	"""Override of ERPNext's list-view close action, with the same rule as update_status."""
	parsed = frappe.parse_json(names)
	if status == "Closed":
		ensure_short_close_reason(parsed)
	else:
		for name in parsed:
			clear_short_close(name)
	return erpnext_po.close_or_unclose_purchase_orders(names, status)


def ensure_short_close_reason(names):
	pending = [
		name
		for name in names
		if frappe.db.get_value("Purchase Order", name, "status") in OPEN_STATUSES
	]
	if pending:
		frappe.throw(
			_("{0} still awaiting goods. Use Short Close and give a reason.").format(", ".join(pending)),
			title=_("Short-close reason required"),
		)


def clear_short_close(name):
	if frappe.db.get_value("Purchase Order", name, "nir_short_close_reason"):
		frappe.db.set_value(
			"Purchase Order",
			name,
			{
				"nir_short_close_reason": None,
				"nir_short_close_remarks": None,
				"nir_short_closed_by": None,
				"nir_short_closed_on": None,
			},
		)


# Fill rate and lead time per PO


def update_from_receipt(doc, method=None):
	"""Purchase Receipt / Purchase Invoice (update stock) submit or cancel: refresh linked POs."""
	if doc.doctype == "Purchase Invoice" and not doc.update_stock:
		return

	for name in {row.purchase_order for row in doc.items if row.get("purchase_order")}:
		update_fulfilment(name)


def update_fulfilment(purchase_order):
	po = frappe.db.get_value(
		"Purchase Order",
		purchase_order,
		["name", "status", "transaction_date", "schedule_date", "nir_po_sent_on", "nir_expected_delivery_date"],
		as_dict=True,
	)
	lines = get_line_supply(purchase_order)
	if not lines:
		return

	ordered = sum(line.ordered for line in lines)
	filled = sum(min(line.accepted, line.ordered) for line in lines)
	full_lines = sum(1 for line in lines if line.accepted >= line.ordered)
	receipt_dates = sorted(d for line in lines for d in line.receipt_dates)

	start = getdate(po.nir_po_sent_on or po.transaction_date)
	first_receipt = receipt_dates[0] if receipt_dates else None
	fully_received = full_lines == len(lines)
	last_receipt = receipt_dates[-1] if receipt_dates else None

	on_time = None
	if fully_received or po.status == "Closed":
		due = getdate(po.nir_expected_delivery_date or po.schedule_date)
		on_time = "Yes" if fully_received and last_receipt and last_receipt <= due else "No"

	frappe.db.set_value(
		"Purchase Order",
		purchase_order,
		{
			"nir_qty_fill_rate": flt(filled / ordered * 100, 2) if ordered else 0,
			"nir_line_fill_rate": flt(full_lines / len(lines) * 100, 2),
			"nir_backorder_qty": max(ordered - filled, 0),
			"nir_first_receipt_date": first_receipt,
			# number columns can't hold NULL: 0 until there is a receipt (reports check the receipt date)
			"nir_lead_time_days": date_diff(first_receipt, start) if first_receipt else 0,
			"nir_full_receipt_lead_time_days": date_diff(last_receipt, start) if fully_received else 0,
			"nir_on_time": on_time or "",
		},
		update_modified=False,
	)


def get_line_supply(purchase_order):
	"""Ordered vs accepted stock qty per PO line (free scheme rows excluded), with receipt dates.

	Accepted qty nets off purchase returns; rejected qty never counts as supplied.
	"""
	po_items = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": purchase_order, "is_free_item": 0},
		fields=["name", "item_code", "stock_qty", "expected_delivery_date", "schedule_date"],
		order_by="idx asc",
	)
	if not po_items:
		return []

	receipts = frappe.db.sql(
		"""
		select pri.purchase_order_item as po_item, pr.posting_date, pri.stock_qty
		from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent
		where pri.purchase_order = %(po)s and pr.docstatus = 1
		union all
		select pii.po_detail, pi.posting_date, pii.stock_qty
		from `tabPurchase Invoice Item` pii
		join `tabPurchase Invoice` pi on pi.name = pii.parent
		where pii.purchase_order = %(po)s and pi.docstatus = 1 and pi.update_stock = 1
		""",
		{"po": purchase_order},
		as_dict=True,
	)

	lines = []
	for item in po_items:
		rows = [r for r in receipts if r.po_item == item.name]
		lines.append(
			frappe._dict(
				name=item.name,
				item_code=item.item_code,
				ordered=flt(item.stock_qty),
				accepted=sum(flt(r.stock_qty) for r in rows),
				due=getdate(item.expected_delivery_date or item.schedule_date),
				receipt_dates=[getdate(r.posting_date) for r in rows if flt(r.stock_qty) > 0],
			)
		)
	return lines


# Backorder follow-up


def send_backorder_followups():
	"""Daily: chase suppliers for overdue pending lines, every N days until supplied or short-closed."""
	days = cint(frappe.db.get_single_value("Buying Settings", "nir_backorder_followup_days")) or DEFAULT_FOLLOWUP_DAYS
	last_allowed = add_days(today(), -days)

	for name in frappe.get_all(
		"Purchase Order",
		filters={"docstatus": 1, "status": ("in", OPEN_STATUSES)},
		or_filters=[
			["nir_backorder_followup_on", "is", "not set"],
			["nir_backorder_followup_on", "<=", last_allowed],
		],
		pluck="name",
	):
		overdue = [
			line for line in get_line_supply(name) if line.accepted < line.ordered and line.due < getdate(today())
		]
		if overdue:
			follow_up(name, overdue)


def follow_up(purchase_order, overdue):
	po = frappe.get_doc("Purchase Order", purchase_order)
	notify_buyer(
		po,
		_("{0} lines on Purchase Order {1} from {2} are overdue").format(
			len(overdue), po.name, po.supplier_name or po.supplier
		),
	)

	recipient = get_supplier_email(po)
	if recipient:
		rows = "".join(
			f"<tr><td>{frappe.utils.escape_html(line.item_code)}</td><td>{flt(line.ordered)}</td>"
			f"<td>{flt(line.accepted)}</td><td>{flt(line.ordered - line.accepted)}</td>"
			f"<td>{frappe.format(line.due, 'Date')}</td></tr>"
			for line in overdue
		)
		content = _(
			"<p>The following items on Purchase Order {0} are past their delivery date and still pending:</p>"
			"<table border='1' cellpadding='4'><tr><th>Item</th><th>Ordered</th><th>Received</th>"
			"<th>Pending</th><th>Due</th></tr>{1}</table>"
			'<p>Please supply them or confirm new delivery dates on our portal: <a href="{2}">{2}</a></p>'
		).format(po.name, rows, get_url(f"{ACK_PAGE}?name={po.name}"))
		try:
			make(
				doctype=po.doctype,
				name=po.name,
				recipients=recipient,
				subject=_("Pending supply on Purchase Order {0}").format(po.name),
				content=content,
				send_email=True,
			)
		except frappe.OutgoingEmailError:
			po.add_comment("Comment", _("Backorder follow-up not emailed: outgoing email is not set up"))

	frappe.db.set_value(
		"Purchase Order",
		po.name,
		{"nir_backorder_followup_on": today(), "nir_backorder_followups": cint(po.nir_backorder_followups) + 1},
		update_modified=False,
	)


# Supplier performance


def get_supplier_performance(from_date, to_date, company=None, supplier=None):
	"""Per supplier: fill rates over POs whose supply is final, lead time and on-time over POs received."""
	filters = {"docstatus": 1, "transaction_date": ("between", (from_date, to_date))}
	if company:
		filters["company"] = company
	if supplier:
		filters["supplier"] = supplier

	pos = frappe.get_all(
		"Purchase Order",
		filters=filters,
		fields=[
			"supplier",
			"status",
			"nir_qty_fill_rate",
			"nir_line_fill_rate",
			"nir_lead_time_days",
			"nir_first_receipt_date",
			"nir_on_time",
			"nir_short_close_reason",
			"nir_backorder_qty",
		],
	)

	stats = {}
	for po in pos:
		s = stats.setdefault(
			po.supplier,
			frappe._dict(pos=0, final=0, qty_fill=0.0, line_fill=0.0, lead=[], on_time=0, timed=0, short=0, backorder=0.0),
		)
		s.pos += 1
		if po.status in FINAL_STATUSES:
			s.final += 1
			s.qty_fill += flt(po.nir_qty_fill_rate)
			s.line_fill += flt(po.nir_line_fill_rate)
		if po.nir_first_receipt_date:
			s.lead.append(cint(po.nir_lead_time_days))
		if po.nir_on_time:
			s.timed += 1
			s.on_time += po.nir_on_time == "Yes"
		if po.nir_short_close_reason:
			s.short += 1
		if po.status in OPEN_STATUSES:
			s.backorder += flt(po.nir_backorder_qty)

	return {
		supplier: frappe._dict(
			purchase_orders=s.pos,
			completed_orders=s.final,
			qty_fill_rate=flt(s.qty_fill / s.final, 2) if s.final else None,
			line_fill_rate=flt(s.line_fill / s.final, 2) if s.final else None,
			avg_lead_time=flt(sum(s.lead) / len(s.lead), 1) if s.lead else None,
			on_time_pct=flt(s.on_time / s.timed * 100, 2) if s.timed else None,
			short_closed=s.short,
			pending_qty=s.backorder,
		)
		for supplier, s in stats.items()
	}


def update_supplier_performance():
	"""Daily: rolling 90-day fill rate, lead time and on-time % on each supplier."""
	performance = get_supplier_performance(add_days(today(), -PERFORMANCE_WINDOW_DAYS), today())
	for supplier, p in performance.items():
		# set_value, not save: these are system figures and must not trip the supplier maker-checker
		frappe.db.set_value(
			"Supplier",
			supplier,
			{
				"nir_fill_rate_90d": p.qty_fill_rate or 0,
				"nir_on_time_pct_90d": p.on_time_pct or 0,
				"nir_avg_lead_time_90d": p.avg_lead_time or 0,
				"nir_performance_updated_on": today(),
			},
			update_modified=False,
		)
