# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Store receiving (ST-02): by tote scan, tote-level or full check by store type, discrepancies within a window."""

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_inter_company_purchase_invoice
from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.controlled_drugs import CONTROLLED_CATEGORIES
from pharmacy.overrides.store_transfer import get_shipments, get_trip_info

DEFAULT_WINDOW_HOURS = 24
TOTE_LEVEL_GRADES = ("A", "B")


class StoreReceipt(Document):
	def before_submit(self):
		unscanned = [t.tote for t in self.totes if not t.scanned]
		if unscanned and not self.auto_received:
			frappe.throw(_("Scan every tote first: {0}").format(", ".join(unscanned)))
		unchecked = [f"#{r.idx} {r.item_code}" for r in self.items if not r.checked and not self.auto_received]
		if unchecked:
			frappe.throw(_("Check these lines (scan item / batch and enter qty): {0}").format(", ".join(unchecked)))

		self.has_differences = any(differences(r) for r in self.items)
		if self.has_differences and self.window_ends and now_datetime() > get_datetime(self.window_ends):
			frappe.throw(_("The window to report discrepancies closed at {0}; receive as dispatched or raise a manual adjustment").format(
				frappe.format(self.window_ends, "Datetime")))
		self.status = "Auto-Received" if self.auto_received else ("Received with Discrepancy" if self.has_differences else "Received")

	def on_submit(self):
		if self.dispatch_doctype == "Stock Entry":
			self.db_set("stock_entry", receive_from_transit(self))
		elif frappe.db.get_value("Warehouse", self.store_warehouse, "company") != frappe.db.get_value("Sales Invoice", self.dispatch_name, "company"):
			self.db_set("inter_company_invoice", draft_inter_company_invoice(self))

		if any(differences(r) for r in self.items):
			self.db_set("transfer_discrepancy", raise_discrepancy(self))


def differences(row):
	return flt(row.received_qty) != flt(row.dispatched_qty) or flt(row.damaged_qty) > 0


def receive_from_transit(receipt):
	"""ERPNext's end-transit entry for what actually arrived; any shortfall stays in transit for investigation."""
	received = {r.source_row: min(flt(r.received_qty), flt(r.dispatched_qty)) for r in receipt.items}
	entry = make_stock_in_entry(receipt.dispatch_name)
	entry.items = [row for row in entry.items if received.get(row.ste_detail, 0) > 0]
	for row in entry.items:
		row.qty = received[row.ste_detail]
		row.t_warehouse = receipt.store_warehouse
		# the outgoing challan already counted against the indent; counting the receipt too would exceed it
		row.material_request = row.material_request_item = None
	if not entry.items:
		return None
	entry.nir_destination_store = receipt.store_warehouse
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry.name


def draft_inter_company_invoice(receipt):
	"""Store of another company: draft its purchase invoice for the qty actually received."""
	invoice = make_inter_company_purchase_invoice(receipt.dispatch_name)
	received = {(r.item_code, r.batch_no or ""): flt(r.received_qty) for r in receipt.items}
	for row in invoice.items:
		row.qty = received.get((row.item_code, row.batch_no or ""), row.qty) / (flt(row.conversion_factor) or 1)
	invoice.items = [row for row in invoice.items if flt(row.qty) > 0]
	invoice.flags.ignore_permissions = True
	invoice.insert()
	return invoice.name


def raise_discrepancy(receipt):
	lines = []
	for r in receipt.items:
		rate = valuation_rate(r.item_code, r.source_warehouse)
		short = flt(r.dispatched_qty) - flt(r.received_qty)
		if short > 0:
			lines.append(line(r, "Short", short, rate))
		elif short < 0:
			lines.append(line(r, "Excess", -short, rate))
		if flt(r.damaged_qty) > 0:
			lines.append(line(r, "Damaged", flt(r.damaged_qty), rate))
	doc = frappe.get_doc(
		{
			"doctype": "Transfer Discrepancy",
			"company": receipt.company,
			"store_warehouse": receipt.store_warehouse,
			"store_receipt": receipt.name,
			"dispatch_doctype": receipt.dispatch_doctype,
			"dispatch_name": receipt.dispatch_name,
			"items": lines,
			"total_value": sum(l["value"] for l in lines),
		}
	).insert(ignore_permissions=True)
	for user in get_users_with_role("Warehouse Manager"):
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": doc.doctype,
			"document_name": doc.name, "subject": _("{0} reported a discrepancy on {1}").format(receipt.store_warehouse, receipt.dispatch_name)}
		).insert(ignore_permissions=True)
	return doc.name


def line(row, kind, qty, rate):
	return {"item_code": row.item_code, "batch_no": row.batch_no, "discrepancy_type": kind, "qty": qty,
		"value": qty * rate, "source_warehouse": row.source_warehouse}


def valuation_rate(item_code, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")) or flt(
		frappe.db.get_value("Item", item_code, "valuation_rate"))


def get_check_level(store):
	level, grade = frappe.db.get_value("Pharmacy Store", {"warehouse": store}, ["nir_receiving_check", "store_grade"]) or (None, None)
	return level or ("Tote Level" if grade in TOTE_LEVEL_GRADES else "Full Check")


@frappe.whitelist()
def create_store_receipt(dispatch_doctype: str, dispatch_name: str):
	frappe.has_permission("Store Receipt", "create", throw=True)
	return build_receipt(dispatch_doctype, dispatch_name).insert().name


def build_receipt(dispatch_doctype, dispatch_name):
	existing = frappe.db.exists("Store Receipt", {"dispatch_name": dispatch_name, "docstatus": ("<", 2)})
	if existing:
		frappe.throw(_("{0} already has receipt {1}").format(dispatch_name, existing))

	source = frappe.get_doc(dispatch_doctype, dispatch_name)
	store = source.get("nir_destination_store") or source.get("set_target_warehouse")
	trip = get_trip_info(dispatch_name, store)
	delivered = trip.delivered_on or now_datetime()
	hours = cint(frappe.db.get_single_value("Stock Settings", "nir_store_discrepancy_hours")) or DEFAULT_WINDOW_HOURS

	tote_of = {}
	if source.get("nir_pick_wave"):
		for r in frappe.get_all("Pick Wave Item", filters={"parent": source.nir_pick_wave, "store_warehouse": store},
				fields=["item_code", "batch_no", "tote"]):
			tote_of[(r.item_code, r.batch_no or "")] = r.tote

	receipt = frappe.get_doc({
		"doctype": "Store Receipt",
		"company": source.company,
		"store_warehouse": store,
		"dispatch_doctype": dispatch_doctype,
		"dispatch_name": dispatch_name,
		"check_level": get_check_level(store),
		"delivered_on": delivered,
		"window_ends": add_to_date(delivered, hours=hours),
	})
	for row in source.items:
		item = frappe.get_cached_value("Item", row.item_code, ["nir_storage_condition", "nir_regulatory_category"], as_dict=True)
		qty = flt(row.get("transfer_qty") or row.get("stock_qty"))
		receipt.append("items", {
			"item_code": row.item_code, "batch_no": row.batch_no, "dispatched_qty": qty, "received_qty": 0,
			"tote": tote_of.get((row.item_code, row.batch_no or "")), "source_row": row.name,
			"source_warehouse": row.get("s_warehouse") or row.get("warehouse"), "stock_uom": row.stock_uom,
			# controlled and cold-chain lines are always counted, whatever the store's check level
			"full_check": int(item.nir_regulatory_category in CONTROLLED_CATEGORIES or item.nir_storage_condition == "2-8C"),
		})
	for t in frappe.get_all("Tote", filters={"dispatch_name": dispatch_name}, fields=["name", "tote_type", "seal_no"]):
		receipt.append("totes", {"tote": t.name, "tote_type": t.tote_type, "seal_no": t.seal_no})
	return receipt


def get_draft(receipt):
	doc = frappe.get_doc("Store Receipt", receipt)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted").format(doc.name))
	return doc


@frappe.whitelist()
def scan_tote(receipt: str, tote: str, seal_intact: str):
	doc = get_draft(receipt)
	tote = (tote or "").strip().upper()
	row = next((t for t in doc.totes if t.tote == tote), None)
	if not row:
		frappe.throw(_("Tote {0} is not part of this shipment").format(tote))
	row.scanned = 1
	row.seal_intact = "Intact" if seal_intact == "Intact" else "Broken"
	for item in doc.items:
		if item.tote != tote:
			continue
		if row.seal_intact == "Broken":
			item.full_check = 1
		elif doc.check_level == "Tote Level" and not item.full_check:
			# an intact seal vouches for the tote's contents
			item.received_qty = item.dispatched_qty
			item.checked = 1
	doc.save()
	return {"scanned": sum(t.scanned for t in doc.totes), "of": len(doc.totes), "seal": row.seal_intact}


@frappe.whitelist()
def scan_item(receipt: str, code: str, qty: float, damaged_qty: float = 0):
	doc = get_draft(receipt)
	code = (code or "").strip()
	item_code = frappe.db.get_value("Batch", code, "item") or frappe.db.get_value("Item Barcode", {"barcode": code}, "parent") or code
	row = next((r for r in doc.items if r.item_code == item_code and (not r.batch_no or r.batch_no == code)), None)
	if not row:
		frappe.throw(_("{0} is not on this shipment; report it in the discrepancy after receiving").format(code))
	row.received_qty = flt(qty)
	row.damaged_qty = flt(damaged_qty)
	row.checked = 1
	doc.save()
	return {"item_code": row.item_code, "checked": sum(r.checked for r in doc.items), "of": len(doc.items)}


def auto_receive_overdue():
	"""Hourly: shipments delivered more than the window ago without a receipt are received as dispatched."""
	for shipment in get_shipments():
		trip = get_trip_info(shipment.name, shipment.store)
		if not trip.delivered_on:
			continue
		hours = cint(frappe.db.get_single_value("Stock Settings", "nir_store_discrepancy_hours")) or DEFAULT_WINDOW_HOURS
		if now_datetime() < add_to_date(trip.delivered_on, hours=hours):
			continue
		# an unfinished draft is replaced: past the window the shipment counts as received in full
		for draft in frappe.get_all("Store Receipt", filters={"dispatch_name": shipment.name, "docstatus": 0}, pluck="name"):
			frappe.delete_doc("Store Receipt", draft, ignore_permissions=True)
		receipt = build_receipt(shipment.doctype, shipment.name)
		receipt.auto_received = 1
		for row in receipt.items:
			row.received_qty, row.checked = row.dispatched_qty, 1
		for t in receipt.totes:
			t.scanned, t.seal_intact = 1, "Intact"
		receipt.flags.ignore_permissions = True
		receipt.insert()
		receipt.submit()
