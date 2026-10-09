"""Inbound: gate entry, GRN against PO by scan, receipt checks, cold chain quarantine and discrepancies.

Each GRN line gets a list of flags on validate, so problems show while the receipt is still a draft;
blocking flags then stop the submit.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, now_datetime
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.putaway import route_from_dc, route_to_cage
from pharmacy.overrides.shelf_life import get_shelf_life_threshold
from pharmacy.overrides.warehouse_layout import get_layout

# acceptable reading (°C) per storage condition: (min, max)
TEMPERATURE_RANGE = {"2-8C": (2, 8), "Below 25C": (None, 25)}
# a quarantine zone may hold an item if it is at least as cold as the item needs
COMPATIBLE_ZONES = {"2-8C": ("2-8C",), "Below 25C": ("Below 25C", "2-8C"), "Ambient": ("Ambient", "Below 25C", "2-8C", None, "")}
MRP_APPROVER_ROLE = "Category Manager"
QA_ROLES = ("Compliance Pharmacist", "Warehouse Manager")

NOT_ON_PO = "Not on PO"
OVER_PO = "Qty exceeds PO"
SHORT_SHELF_LIFE = "Shelf life below minimum"
NO_READING = "Temperature reading missing"
BLOCKING = (NOT_ON_PO, OVER_PO, SHORT_SHELF_LIFE, NO_READING)


def is_supplier_receipt(doc):
	return not doc.is_return and doc.doctype == "Purchase Receipt"


# validate


def validate_receipt(doc, method=None):
	if not is_supplier_receipt(doc):
		return

	validate_gate_entry(doc)
	add_free_rows(doc)

	items = get_item_details(doc)
	layout = get_layout(doc.company)
	for row in doc.items:
		item = items.get(row.item_code) or frappe._dict()
		flags = []
		set_batch(doc, row, item)
		# before the cold-chain check, so a breach is quarantined from the bin the line will really go to
		route_flags = route_from_dc(doc, row, item, layout)
		flags += check_po(doc, row)
		flags += check_shelf_life(doc, row)
		flags += check_mrp(row)
		flags += check_cold_chain(doc, row, item)
		flags += route_to_cage(doc, row, item, layout)
		flags += route_flags
		row.nir_receipt_flags = "\n".join(flags) or None

	update_mrp_approval(doc)


def validate_gate_entry(doc):
	if not doc.nir_gate_entry:
		# a GRN made from a PO picks up the gate entry recorded against that PO
		purchase_orders = list({row.purchase_order for row in doc.items if row.purchase_order})
		if purchase_orders:
			doc.nir_gate_entry = frappe.db.get_value(
				"Gate Entry",
				{"purchase_order": ("in", purchase_orders), "supplier": doc.supplier, "docstatus": 1, "status": "Arrived"},
				"name",
				order_by="arrival_time desc",
			)
	if not doc.nir_gate_entry:
		frappe.throw(_("Select the Gate Entry for this delivery"), title=_("Gate Entry required"))

	gate = frappe.db.get_value(
		"Gate Entry", doc.nir_gate_entry, ["docstatus", "supplier", "company", "status"], as_dict=True
	)
	if not gate or gate.docstatus != 1:
		frappe.throw(_("Gate Entry {0} is not submitted").format(doc.nir_gate_entry))
	if gate.supplier != doc.supplier or gate.company != doc.company:
		frappe.throw(_("Gate Entry {0} is for a different supplier or company").format(doc.nir_gate_entry))


def add_free_rows(doc):
	"""Turn each line's free qty into its own zero-rate line, rebuilt on every save so edits stay in step."""
	doc.items = [row for row in doc.items if not row.nir_auto_free]
	for row in list(doc.items):
		if row.is_free_item or flt(row.nir_free_qty) <= 0:
			continue

		po_free_row = None
		if row.purchase_order:
			po_free_row = frappe.db.get_value(
				"Purchase Order Item",
				{"parent": row.purchase_order, "item_code": row.item_code, "is_free_item": 1},
				"name",
			)

		free = doc.append("items", {})
		for field in (
			"item_code", "item_name", "description", "uom", "stock_uom", "conversion_factor", "warehouse",
			"purchase_order", "nir_supplier_batch_no", "nir_mfg_date", "nir_expiry_date", "nir_mrp",
			"nir_temperature", "nir_logger_status", "expense_account", "cost_center",
		):
			free.set(field, row.get(field))
		free.qty = free.received_qty = flt(row.nir_free_qty)
		free.rate = free.price_list_rate = 0
		free.is_free_item = 1
		free.purchase_order_item = po_free_row
		free.nir_auto_free = 1


def get_item_details(doc):
	return {
		item.name: item
		for item in frappe.get_all(
			"Item",
			filters={"name": ("in", list({row.item_code for row in doc.items}))},
			fields=["name", "has_batch_no", "nir_storage_condition", "nir_regulatory_category"],
		)
	}


def set_batch(doc, row, item):
	"""Batch from the supplier's number, dates and MRP, named {item}-{supplier batch}."""
	if not item.has_batch_no or not row.nir_supplier_batch_no:
		return
	row.batch_no = ensure_batch(row.item_code, row.nir_supplier_batch_no, row.nir_mfg_date, row.nir_expiry_date,
		row.nir_mrp, row.uom, doc.supplier)
	row.use_serial_batch_fields = 1


def ensure_batch(item_code, supplier_batch_no, mfg_date, expiry_date, mrp, uom, supplier):
	batch_id = f"{item_code}-{supplier_batch_no.strip()}"
	if not frappe.db.exists("Batch", batch_id):
		frappe.get_doc(
			{
				"doctype": "Batch",
				"batch_id": batch_id,
				"item": item_code,
				"supplier_batch_no": supplier_batch_no,
				"manufacturing_date": mfg_date,
				"expiry_date": expiry_date,
				"nir_mrp": mrp,
				"nir_mrp_uom": uom,
				"supplier": supplier,
			}
		).insert(ignore_permissions=True)
	else:
		# a batch first seen without dates or MRP picks them up from this receipt
		existing = frappe.db.get_value("Batch", batch_id, ["expiry_date", "manufacturing_date", "nir_mrp"], as_dict=True)
		updates = {k: v for k, v in (("expiry_date", expiry_date), ("manufacturing_date", mfg_date), ("nir_mrp", mrp))
			if v and not existing.get(k)}
		if updates:
			frappe.db.set_value("Batch", batch_id, updates)
	return batch_id


def prepare_batches(doc, method=None):
	"""before_validate: fill Batch No ahead of ERPNext's own batch checks."""
	if not is_supplier_receipt(doc):
		return
	for row in doc.items:
		if row.nir_supplier_batch_no and frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
			set_batch(doc, row, frappe._dict(has_batch_no=1))


@frappe.whitelist()
def create_line_batch(item_code: str, supplier_batch_no: str, expiry_date: str, mrp: float, uom: str,
		supplier: str | None = None, mfg_date: str | None = None) -> str | None:
	"""Called from the receipt line as soon as batch no., expiry and MRP are entered."""
	frappe.has_permission("Purchase Receipt", "create", throw=True)
	if not frappe.db.get_value("Item", item_code, "has_batch_no") or not supplier_batch_no:
		return None
	return ensure_batch(item_code, supplier_batch_no, mfg_date, expiry_date, flt(mrp), uom, supplier)


def check_po(doc, row):
	if row.is_free_item:
		# free goods without a scheme row on the PO are welcome; with one, they're held to its qty
		if not row.purchase_order_item:
			return []
	elif not row.purchase_order_item:
		return [NOT_ON_PO]

	ordered = flt(frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "stock_qty"))
	received_before = flt(
		frappe.db.sql(
			"""select sum(pri.received_stock_qty) from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pri.purchase_order_item = %s and pr.docstatus = 1 and pr.name != %s""",
			(row.purchase_order_item, doc.name),
		)[0][0]
	)
	this_receipt = sum(
		(flt(r.qty) + flt(r.rejected_qty)) * (flt(r.conversion_factor) or 1)
		for r in doc.items
		if r.purchase_order_item == row.purchase_order_item
	)
	return [OVER_PO] if received_before + this_receipt > ordered + 0.0001 else []


def check_shelf_life(doc, row):
	if not row.nir_expiry_date:
		return []
	required = get_shelf_life_threshold(row.item_code, "min_days_supplier_receipt")
	if required is None:
		return []
	remaining = date_diff(getdate(row.nir_expiry_date), getdate(doc.posting_date))
	return [f"{SHORT_SHELF_LIFE} ({remaining} of {required} days)"] if remaining < required else []


def check_mrp(row):
	"""Compare with the MRP of the item's most recent other batch, per the same pack."""
	row.nir_previous_mrp = None
	if not flt(row.nir_mrp):
		return []

	previous = frappe.db.sql(
		"""select nir_mrp from `tabBatch`
		where item = %s and name != %s and ifnull(nir_mrp, 0) > 0 and ifnull(nir_mrp_uom, '') = %s
		order by creation desc limit 1""",
		(row.item_code, row.batch_no or "", row.uom or ""),
	)
	if not previous:
		return []

	row.nir_previous_mrp = flt(previous[0][0])
	if abs(flt(row.nir_mrp) - row.nir_previous_mrp) > 0.005:
		return [_("MRP changed from {0}").format(row.nir_previous_mrp)]
	return []


def check_cold_chain(doc, row, item):
	"""Readings are required for temperature-controlled items; an excursion sends the line to quarantine."""
	condition = item.nir_storage_condition
	if condition not in TEMPERATURE_RANGE:
		return []

	reading = parse_temperature(row.nir_temperature)
	if reading is None and row.nir_logger_status not in ("OK", "Excursion"):
		restore_warehouse(row)
		return [NO_READING]

	low, high = TEMPERATURE_RANGE[condition]
	out_of_range = reading is not None and ((low is not None and reading < low) or reading > high)
	if not (out_of_range or row.nir_logger_status == "Excursion"):
		restore_warehouse(row)
		return []

	if not row.nir_quarantined:
		row.nir_intended_warehouse = row.warehouse
		row.warehouse = get_quarantine_warehouse(row.warehouse or doc.set_warehouse, condition)
		row.nir_quarantined = 1
	return [_("Cold chain breach ({0}); sent to quarantine").format(
		f"{reading}°C" if out_of_range else _("logger excursion")
	)]


def parse_temperature(value):
	"""Readings are free text so that blank stays blank (a Float would read as 0 °C)."""
	value = (value or "").strip().replace("°C", "").replace("°", "").strip()
	if not value:
		return None
	try:
		return float(value)
	except ValueError:
		frappe.throw(_("Temperature {0} is not a number").format(frappe.bold(value)))


def restore_warehouse(row):
	"""A corrected reading puts the line back where it was meant to go."""
	if row.nir_quarantined:
		row.warehouse = row.nir_intended_warehouse or row.warehouse
		row.nir_quarantined = 0
		row.nir_intended_warehouse = None


def get_quarantine_warehouse(warehouse, condition):
	"""The Quarantine zone, cold enough for the item, inside the receiving warehouse's DC."""
	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	ancestors = frappe.get_all(
		"Warehouse",
		filters={"lft": ("<=", lft), "rgt": (">=", rgt)},
		fields=["name", "lft", "rgt", "nir_warehouse_role"],
		order_by="lft desc",
	)
	site = next((w for w in ancestors if w.nir_warehouse_role == "DC"), ancestors[-1])

	zones = frappe.get_all(
		"Warehouse",
		filters={"lft": (">", site.lft), "rgt": ("<", site.rgt), "nir_zone_type": "Quarantine", "is_group": 0},
		fields=["name", "nir_storage_condition"],
	)
	allowed = COMPATIBLE_ZONES.get(condition, (condition,))
	match = next((z.name for z in zones if z.nir_storage_condition in allowed), None)
	if not match:
		frappe.throw(
			_("No {0} Quarantine bin under {1}. Create one to receive this stock.").format(condition, site.name),
			title=_("Quarantine warehouse missing"),
		)
	return match


def get_mrp_changes(doc):
	return sorted(
		(row.item_code, row.uom or "", flt(row.nir_mrp))
		for row in doc.items
		if row.nir_previous_mrp and abs(flt(row.nir_mrp) - flt(row.nir_previous_mrp)) > 0.005
	)


def update_mrp_approval(doc):
	"""MRP changes need a Category Manager's approval; changing an approved MRP asks again."""
	changes = get_mrp_changes(doc)
	signature = hashlib.sha1(json.dumps(changes).encode()).hexdigest() if changes else None
	doc.nir_mrp_change_pending = int(bool(changes) and signature != doc.nir_mrp_change_signature)
	if not changes:
		doc.nir_mrp_change_signature = doc.nir_mrp_change_approved_by = doc.nir_mrp_change_approved_on = None


@frappe.whitelist()
def approve_mrp_change(purchase_receipt: str):
	doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
	doc.check_permission("read")
	if MRP_APPROVER_ROLE not in frappe.get_roles():
		frappe.throw(_("Only a {0} can approve MRP changes").format(MRP_APPROVER_ROLE), frappe.PermissionError)
	if frappe.session.user == doc.owner:
		frappe.throw(_("You created this receipt, so someone else must approve its MRP changes."))
	if doc.docstatus != 0 or not doc.nir_mrp_change_pending:
		frappe.throw(_("No MRP change is waiting for approval on {0}").format(doc.name))

	changes = get_mrp_changes(doc)
	doc.nir_mrp_change_signature = hashlib.sha1(json.dumps(changes).encode()).hexdigest()
	doc.nir_mrp_change_approved_by = frappe.session.user
	doc.nir_mrp_change_approved_on = now_datetime()
	doc.flags.ignore_permissions = True
	doc.save()
	doc.add_comment("Comment", _("MRP changes approved"))


# submit


def validate_before_submit(doc, method=None):
	if not is_supplier_receipt(doc):
		return

	blocked = [
		f"#{row.idx} {row.item_code}: {flag}"
		for row in doc.items
		for flag in (row.nir_receipt_flags or "").split("\n")
		if flag.startswith(BLOCKING)
	]
	if blocked:
		frappe.throw("<br>".join(blocked), title=_("Receipt blocked"))
	if doc.nir_mrp_change_pending:
		frappe.throw(_("MRP changes on this receipt need a {0}'s approval").format(MRP_APPROVER_ROLE))


def on_submit(doc, method=None):
	if not is_supplier_receipt(doc):
		return

	frappe.db.set_value("Gate Entry", doc.nir_gate_entry, "status", "Received")
	raise_quarantine_decisions(doc)
	raise_discrepancy(doc)


def on_cancel(doc, method=None):
	if not is_supplier_receipt(doc) or not doc.nir_gate_entry:
		return
	other = frappe.db.exists(
		"Purchase Receipt", {"nir_gate_entry": doc.nir_gate_entry, "docstatus": 1, "name": ("!=", doc.name)}
	)
	if not other:
		frappe.db.set_value("Gate Entry", doc.nir_gate_entry, "status", "Arrived")


def raise_quarantine_decisions(doc):
	decisions = []
	for row in doc.items:
		if not row.nir_quarantined:
			continue
		decision = frappe.get_doc(
			{
				"doctype": "Quarantine Decision",
				"company": doc.company,
				"purchase_receipt": doc.name,
				"item_code": row.item_code,
				"batch_no": row.batch_no,
				"qty": flt(row.stock_qty),
				"quarantine_warehouse": row.warehouse,
				"temperature": row.nir_temperature,
				"logger_status": row.nir_logger_status,
				"reason": row.nir_receipt_flags,
				"target_warehouse": row.nir_intended_warehouse,
			}
		).insert(ignore_permissions=True)
		decisions.append(decision.name)

	if decisions:
		users = {user for role in QA_ROLES for user in get_users_with_role(role)}
		notify(users, doc, _("Quarantine decisions {0} needed for {1}").format(", ".join(decisions), doc.name))


def raise_discrepancy(doc):
	"""Damage (rejected qty) and shortage or excess against the supplier invoice qty go on a draft note."""
	lines = []
	for row in doc.items:
		received = flt(row.qty) + flt(row.rejected_qty)
		if flt(row.rejected_qty):
			lines.append(discrepancy_line(row, "Damage", flt(row.rejected_qty), received))
		# 0 means not entered: Float fields can't be blank
		if flt(row.nir_invoiced_qty) > 0 and abs(flt(row.nir_invoiced_qty) - received) > 0.0001:
			kind = "Shortage" if flt(row.nir_invoiced_qty) > received else "Excess"
			lines.append(discrepancy_line(row, kind, abs(flt(row.nir_invoiced_qty) - received), received))

	if not lines:
		return

	note = frappe.get_doc(
		{
			"doctype": "Receipt Discrepancy",
			"company": doc.company,
			"purchase_receipt": doc.name,
			"gate_entry": doc.nir_gate_entry,
			"supplier": doc.supplier,
			"posting_date": doc.posting_date,
			"items": lines,
		}
	).insert(ignore_permissions=True)
	doc.db_set("nir_receipt_discrepancy", note.name)
	notify({doc.owner}, doc, _("Add photos and submit discrepancy note {0} for {1}").format(note.name, doc.name))


def discrepancy_line(row, kind, qty, received):
	return {
		"item_code": row.item_code,
		"batch_no": row.batch_no,
		"discrepancy_type": kind,
		"invoiced_qty": row.nir_invoiced_qty,
		"received_qty": received,
		"discrepancy_qty": qty,
	}


def notify(users, doc, subject):
	for user in users:
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


# scanning


@frappe.whitelist()
def resolve_scan(barcode: str, supplier: str, company: str) -> dict:
	"""Item for a scanned barcode (or item code), and the open PO line from this supplier to receive it against."""
	frappe.has_permission("Purchase Receipt", "create", throw=True)

	barcode = (barcode or "").strip()
	item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent") or (
		barcode if frappe.db.exists("Item", barcode) else None
	)
	if not item_code:
		frappe.throw(_("No item has barcode {0}").format(barcode))

	item = frappe.db.get_value(
		"Item", item_code, ["item_name", "stock_uom", "purchase_uom", "nir_storage_condition"], as_dict=True
	)
	po_line = frappe.db.sql(
		"""select poi.name, poi.parent, poi.uom, poi.conversion_factor, poi.rate, poi.warehouse,
			poi.qty - ifnull(poi.received_qty, 0) as pending_qty
		from `tabPurchase Order Item` poi
		join `tabPurchase Order` po on po.name = poi.parent
		where po.supplier = %(supplier)s and po.company = %(company)s and po.docstatus = 1
			and po.status in ('To Receive', 'To Receive and Bill')
			and poi.item_code = %(item)s and ifnull(poi.is_free_item, 0) = 0
			and poi.received_qty < poi.qty
		order by poi.schedule_date asc, po.transaction_date asc
		limit 1""",
		{"supplier": supplier, "company": company, "item": item_code},
		as_dict=True,
	)
	line = po_line[0] if po_line else None
	return {
		"item_code": item_code,
		"item_name": item.item_name,
		"uom": line.uom if line else (item.purchase_uom or item.stock_uom),
		"conversion_factor": line.conversion_factor if line else 1,
		"rate": line.rate if line else 0,
		"warehouse": line.warehouse if line else None,
		"purchase_order": line.parent if line else None,
		"purchase_order_item": line.name if line else None,
		"pending_qty": line.pending_qty if line else 0,
		"cold_chain": item.nir_storage_condition in TEMPERATURE_RANGE,
	}
