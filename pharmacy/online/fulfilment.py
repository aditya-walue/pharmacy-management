"""Online Sales Orders: pharmacist prescription check, allocation to stores / DC, billing by the dispatching location, delivery.

Allocation: the nearest location serving the pincode that can fill the whole order gets it. Otherwise, by the
Online Order Settings, the order is split line by line across locations (Split), or kept at one store with a
transfer raised for what it is missing (Transfer to One Location; store pickups always work this way).
Each location bills its own lines from its own stock, under its own GSTIN address.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate

from pharmacy.online import get_settings
from pharmacy.online.catalog import available_qty, get_locations, sellable_warehouses
from pharmacy.overrides.pos_billing import check_batch, pick_batch, uom_factor
from pharmacy.overrides.stock_hold import get_active_holds

PHARMACIST_ROLE = "Online Order Pharmacist"
BILLING_ROLES = ("Store Pharmacist", "Online Order Pharmacist", "Warehouse Manager", "System Manager")


def online_order(name, statuses=None):
	so = frappe.get_doc("Sales Order", name)
	if not so.nir_is_online_order:
		frappe.throw(_("{0} is not an online order").format(name))
	if statuses and so.nir_online_status not in statuses:
		frappe.throw(_("Order {0} is {1}").format(name, so.nir_online_status))
	return so


def require_role(roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Only {0} can do this").format(" / ".join(roles)), frappe.PermissionError)


# ---- pharmacist check


@frappe.whitelist()
def approve_prescription(sales_order: str, doctor_name: str, doctor_reg_no: str, patient_name: str | None = None,
		remarks: str | None = None, valid_upto: str | None = None):
	"""Rx items are released only after this check; it is logged on the order and the prescription is saved."""
	require_role((PHARMACIST_ROLE, "System Manager"))
	so = online_order(sales_order, ("Prescription Review",))
	if frappe.session.user == so.nir_website_user:
		frappe.throw(_("You placed this order, so another pharmacist must check it"))
	so.nir_doctor_name, so.nir_doctor_reg_no = doctor_name, doctor_reg_no
	so.nir_online_patient_name = patient_name or so.nir_online_patient_name or so.customer_name
	so.nir_review_status, so.nir_reviewed_by, so.nir_reviewed_on = "Approved", frappe.session.user, now_datetime()
	so.nir_review_remarks = remarks
	so.append("nir_review_log", {"action": "Approved", "reviewed_by": frappe.session.user, "reviewed_on": now_datetime(),
		"prescription": so.nir_prescription, "remarks": remarks})
	if not so.nir_customer_prescription:
		rx = frappe.get_doc({
			"doctype": "Customer Prescription", "customer": so.customer, "patient_name": so.nir_online_patient_name,
			"prescription_date": nowdate(), "valid_upto": valid_upto or frappe.utils.add_days(nowdate(), cint(get_settings().prescription_validity_days) or 180),
			"doctor_name": doctor_name, "doctor_reg_no": doctor_reg_no, "prescription_file": so.nir_prescription,
			"notes": ", ".join(r.item_name for r in so.items),
		}).insert(ignore_permissions=True)
		so.nir_customer_prescription = rx.name
	so.flags.ignore_permissions = True
	so.save()
	confirm_order(so)
	return frappe.db.get_value("Sales Order", so.name, "nir_online_status")


@frappe.whitelist()
def reject_prescription(sales_order: str, remarks: str):
	require_role((PHARMACIST_ROLE, "System Manager"))
	if not remarks:
		frappe.throw(_("Tell the customer why the prescription was rejected"))
	so = online_order(sales_order, ("Prescription Review",))
	so.nir_review_status, so.nir_reviewed_by, so.nir_reviewed_on = "Rejected", frappe.session.user, now_datetime()
	so.nir_review_remarks = remarks
	so.append("nir_review_log", {"action": "Rejected", "reviewed_by": frappe.session.user, "reviewed_on": now_datetime(),
		"prescription": so.nir_prescription, "remarks": remarks})
	so.flags.ignore_permissions = True
	so.save()
	close_order(so, "Rejected", remarks)
	return "Rejected"


# ---- allocation


def confirm_order(so):
	"""Allocate the lines, raise transfers, submit the Sales Order, then ask for payment (online) or confirm (COD)."""
	settings = get_settings()
	pickup = so.nir_fulfilment_type == "Store Pickup"
	locations = get_locations(so.nir_pincode, so.nir_pickup_store if pickup else None)
	if pickup and settings.dc_warehouse:
		# the pickup store is topped up from the DC when it is short
		locations.append(frappe._dict(store=None, warehouse=settings.dc_warehouse, hours=cint(settings.dc_delivery_hours) or 48,
			cod=1, distance=9999, delivery_type="Standard"))
	if not locations:
		frappe.throw(_("No location serves pincode {0}").format(so.nir_pincode))

	lines = [line_need(row) for row in so.items]
	plan, transfers = plan_allocation(lines, locations, settings, pickup, so.nir_pickup_store)
	apply_plan(so, plan, locations)
	set_expected_by(so, locations, transfers)
	so.flags.ignore_permissions = True
	so.submit()
	for transfer in transfers:
		raise_transfer(so, transfer)

	so.reload()
	if so.nir_payment_method == "Online" and so.nir_payment_status != "Paid":
		from pharmacy.online.payment import create_payment_request

		create_payment_request(so)
		so.db_set("nir_online_status", "Awaiting Payment")
	else:
		so.db_set("nir_online_status", "Confirmed")
		notify_locations(so)


def set_expected_by(so, locations, transfers):
	"""The slowest location used; a transfer adds the DC delivery time."""
	from pharmacy.online.catalog import expected_by

	used = {f.warehouse for f in so.nir_fulfilments}
	hours = max(cint(loc.hours) for loc in locations if loc.warehouse in used)
	if transfers:
		hours += cint(get_settings().dc_delivery_hours) or 24
	so.nir_expected_by = expected_by(hours)
	so.delivery_date = so.nir_expected_by.date()
	for row in so.items:
		row.delivery_date = so.delivery_date


def line_need(row):
	stock_uom = frappe.get_cached_value("Item", row.item_code, "stock_uom")
	factor = flt(row.conversion_factor) or uom_factor(row.item_code, row.uom, stock_uom)
	return frappe._dict(row=row, item_code=row.item_code, need=flt(row.qty) * factor, factor=factor)


def plan_allocation(lines, locations, settings, pickup, pickup_store):
	"""Returns ({row name: [(bin, stock qty)]}, [transfer]) where a transfer is (item, qty, from bin, to warehouse)."""
	stock = {(loc.warehouse, line.item_code): available_qty(line.item_code, loc.warehouse) for loc in locations for line in lines}

	def take(loc, line, qty):
		"""Bins at one location covering qty, fullest bin first."""
		bins, remaining = [], qty
		pool = stock[(loc.warehouse, line.item_code)]
		for leaf, available in sorted(pool.items(), key=lambda kv: -kv[1]):
			if remaining <= 0:
				break
			used = min(available, remaining)
			bins.append((leaf, used))
			pool[leaf] -= used
			remaining -= used
		return bins, remaining

	def total(loc, line):
		return sum(stock[(loc.warehouse, line.item_code)].values())

	# one location for the whole order, nearest first
	for loc in locations:
		if all(total(loc, line) >= line.need for line in lines):
			return {line.row.name: take(loc, line, line.need)[0] for line in lines}, []

	mode = "Transfer to One Location" if pickup else settings.fulfilment_mode
	if mode == "Transfer to One Location":
		stores = [loc for loc in locations if loc.store]
		if not stores:
			mode = "Split"
		else:
			target = stores[0] if pickup else max(stores, key=lambda loc: sum(total(loc, line) >= line.need for line in lines))
			plan, transfers = {}, []
			for line in lines:
				bins, short = take(target, line, line.need)
				for loc in [loc for loc in locations if loc.warehouse != target.warehouse]:
					if short <= 0:
						break
					sources, left = take(loc, line, short)
					transfers += [frappe._dict(item_code=line.item_code, qty=qty, source=leaf, source_store=loc.store,
						target=target.warehouse) for leaf, qty in sources]
					short = left
				if short > 0.0001:
					raise_out_of_stock(line)
				# what arrives by transfer is billed from the store too
				arriving = line.need - sum(q for _leaf, q in bins)
				if arriving > 0:
					bins.append((target.warehouse, arriving))
				plan[line.row.name] = bins
			return plan, transfers

	plan = {}
	for line in lines:
		# a line stays whole at the nearest location that has all of it, else is split by nearest stock
		whole = next((loc for loc in locations if total(loc, line) >= line.need), None)
		if whole:
			plan[line.row.name] = take(whole, line, line.need)[0]
			continue
		bins, short = [], line.need
		for loc in locations:
			got, short = take(loc, line, short)
			bins += got
			if short <= 0:
				break
		if short > 0.0001:
			raise_out_of_stock(line)
		plan[line.row.name] = bins
	return plan, []


def raise_out_of_stock(line):
	frappe.throw(_("{0}: only part of the quantity is in stock. Reduce the quantity or remove it.").format(line.row.item_name),
		title=_("Out of stock"))


def apply_plan(so, plan, locations):
	"""Line warehouses become the fulfilling bins; a line from several bins is split into rows."""
	rows = []
	for row in so.items:
		parts = plan[row.name]
		for i, (leaf, stock_qty) in enumerate(parts):
			new = row if i == 0 else frappe.copy_doc(row)
			new.warehouse = leaf
			new.qty = flt(stock_qty / (flt(row.conversion_factor) or 1), row.precision("qty"))
			rows.append(new)
	so.set("items", [])
	for row in rows:
		so.append("items", row)
	so.calculate_taxes_and_totals()

	so.set("nir_fulfilments", [])
	for warehouse, store in sorted({location_of(r.warehouse, locations) for r in so.items}, key=lambda x: x[0]):
		so.append("nir_fulfilments", {"warehouse": warehouse, "pharmacy_store": store, "status": "Allocated"})


def location_of(warehouse, locations):
	"""The store or DC a bin belongs to."""
	for loc in locations:
		if warehouse == loc.warehouse or warehouse in sellable_warehouses(loc.warehouse):
			return loc.warehouse, loc.store
	return warehouse, frappe.db.get_value("Pharmacy Store", {"warehouse": warehouse})


def raise_transfer(so, transfer):
	"""Store to store: an auto-approved Store Transfer Request. DC to store: a Material Request the DC picks."""
	settings = get_settings()
	if transfer.source_store:
		from pharmacy.pharmacy.doctype.store_transfer_request.store_transfer_request import request_approval

		doc = frappe.get_doc({
			"doctype": "Store Transfer Request", "company": settings.company, "from_store": transfer.source,
			"to_store": transfer.target, "purpose": "Online Order", "online_order": so.name,
			"items": [{"item_code": transfer.item_code, "qty": transfer.qty}],
		}).insert(ignore_permissions=True)
		request_approval(doc.name)
	else:
		doc = frappe.get_doc({
			"doctype": "Material Request", "material_request_type": "Material Transfer", "company": settings.company,
			"transaction_date": nowdate(), "schedule_date": nowdate(), "set_from_warehouse": transfer.source,
			"set_warehouse": transfer.target, "nir_online_sales_order": so.name, "nir_indent_type": None,
			"items": [{"item_code": transfer.item_code, "qty": transfer.qty, "schedule_date": nowdate(),
				"from_warehouse": transfer.source, "warehouse": transfer.target}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
	for f in so.nir_fulfilments:
		if f.warehouse == transfer.target:
			frappe.db.set_value("Online Order Fulfilment", f.name, {"status": "Awaiting Transfer",
				"transfer_doctype": doc.doctype, "transfer_name": doc.name})


def notify_locations(so):
	from frappe.utils.user import get_users_with_role

	users = set(get_users_with_role("Store Pharmacist")) | set(get_users_with_role("Warehouse Manager"))
	for user in users:
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Sales Order",
			"document_name": so.name, "subject": _("Online order {0} to pick and bill").format(so.name)}).insert(ignore_permissions=True)


def on_payment_received(so_name):
	"""Payment Request paid: the order is confirmed and the locations can bill it."""
	so = frappe.get_doc("Sales Order", so_name)
	if not so.nir_is_online_order:
		return
	so.db_set({"nir_payment_status": "Paid", "nir_online_status": "Confirmed" if so.nir_online_status == "Awaiting Payment" else so.nir_online_status})
	notify_locations(so)


# ---- billing by the dispatching location


@frappe.whitelist()
def make_invoice(sales_order: str, warehouse: str):
	"""Draft Sales Invoice for one location's lines, from its stock, earliest-expiry batches, under its GSTIN address."""
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	require_role(BILLING_ROLES)
	so = online_order(sales_order, ("Confirmed", "Partly Dispatched"))
	row = next((f for f in so.nir_fulfilments if f.warehouse == warehouse), None)
	if not row:
		frappe.throw(_("{0} does not fill this order").format(warehouse))
	if row.status == "Awaiting Transfer" and transfer_pending(row):
		frappe.throw(_("Stock for this order is still on transfer {0}").format(row.transfer_name))
	if row.sales_invoice and frappe.db.get_value("Sales Invoice", row.sales_invoice, "docstatus") < 2:
		return row.sales_invoice

	bins = set(sellable_warehouses(warehouse)) | {warehouse}
	si = make_sales_invoice(so.name)
	si.items = [r for r in si.items if r.warehouse in bins]
	if not si.items:
		frappe.throw(_("Nothing left to bill at {0}").format(warehouse))
	for i, r in enumerate(si.items, 1):
		r.idx = i
	si.update_stock = 1
	si.set_warehouse = warehouse if not frappe.db.get_value("Warehouse", warehouse, "is_group") else None
	store_address = frappe.db.get_value("Pharmacy Store", row.pharmacy_store, "address") if row.pharmacy_store else None
	if store_address:
		si.company_address = store_address
	si.nir_prescription, si.nir_doctor_name, si.nir_doctor_reg_no = so.nir_prescription, so.nir_doctor_name, so.nir_doctor_reg_no
	si.nir_patient_name = so.nir_online_patient_name
	si.nir_customer_prescription = so.nir_customer_prescription
	si.allocate_advances_automatically = 1
	si.taxes = [t for t in si.taxes if t.description != "Delivery Charge" or first_invoice(so)]
	if cint(so.loyalty_points) and first_invoice(so) and so.nir_payment_method == "Cash on Delivery":
		si.redeem_loyalty_points, si.loyalty_points = 1, so.loyalty_points

	holds = get_active_holds({r.item_code for r in si.items})
	for r in si.items:
		if not frappe.get_cached_value("Item", r.item_code, "has_batch_no"):
			continue
		if not r.batch_no:
			r.batch_no = pick_batch(r, si, holds)
			r.use_serial_batch_fields = 1
		batch = check_batch(r, si, holds)
		unit_mrp = flt(batch.nir_mrp) / uom_factor(r.item_code, batch.nir_mrp_uom or r.uom, r.stock_uom) * (flt(r.conversion_factor) or 1)
		if flt(r.rate) > unit_mrp + 0.01:
			# a lower-MRP batch is billed at its MRP, never above
			r.rate = unit_mrp
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	si.flags.ignore_permissions = True
	si.insert()
	frappe.db.set_value("Online Order Fulfilment", row.name, "sales_invoice", si.name)
	return si.name


def first_invoice(so):
	return not any(f.sales_invoice for f in so.nir_fulfilments)


def transfer_pending(row):
	if row.transfer_doctype == "Store Transfer Request":
		return frappe.db.get_value("Store Transfer Request", row.transfer_name, "status") != "Dispatched" or not received_at(row)
	if row.transfer_doctype == "Material Request":
		return frappe.db.get_value("Material Request", row.transfer_name, "per_received") < 100
	return False


def received_at(row):
	so = frappe.get_doc("Sales Order", frappe.db.get_value("Online Order Fulfilment", row.name, "parent"))
	return all(available_qty(r.item_code, row.warehouse).get(row.warehouse, 0) >= flt(r.stock_qty)
		for r in so.items if r.warehouse == row.warehouse)


def update_from_invoice(doc, method=None):
	"""Sales Invoice submit / cancel: location status and order status."""
	orders = {r.sales_order for r in doc.items if r.sales_order}
	for name in orders:
		if not frappe.db.get_value("Sales Order", name, "nir_is_online_order"):
			continue
		so = frappe.get_doc("Sales Order", name)
		for f in so.nir_fulfilments:
			if f.sales_invoice != doc.name:
				continue
			if doc.docstatus == 1:
				status = "Ready for Pickup" if so.nir_fulfilment_type == "Store Pickup" else "Billed"
				f.db_set("status", status)
			else:
				f.db_set({"status": "Allocated", "sales_invoice": None})
		refresh_status(so)


def refresh_status(so):
	so.reload()
	statuses = [f.status for f in so.nir_fulfilments if f.status != "Cancelled"]
	if not statuses or so.nir_online_status in ("Cancelled", "Rejected", "Awaiting Payment"):
		return
	if all(s == "Delivered" for s in statuses):
		status = "Delivered"
	elif all(s in ("Billed", "Ready for Pickup", "Out for Delivery", "Delivered") for s in statuses):
		status = "Dispatched"
	elif any(s in ("Billed", "Ready for Pickup", "Out for Delivery", "Delivered") for s in statuses):
		status = "Partly Dispatched"
	else:
		status = "Confirmed"
	so.db_set("nir_online_status", status)


@frappe.whitelist()
def mark_out_for_delivery(sales_order: str, warehouse: str):
	require_role(BILLING_ROLES)
	row = fulfilment(sales_order, warehouse, ("Billed",))
	row.db_set("status", "Out for Delivery")
	refresh_status(frappe.get_doc("Sales Order", sales_order))


@frappe.whitelist()
def mark_delivered(sales_order: str, warehouse: str, cod_amount: float | None = None):
	"""Delivered or picked up; for COD, the cash collected is posted against the invoice."""
	require_role(BILLING_ROLES)
	row = fulfilment(sales_order, warehouse, ("Billed", "Out for Delivery", "Ready for Pickup"))
	so = frappe.get_doc("Sales Order", sales_order)
	if so.nir_payment_method == "Cash on Delivery":
		outstanding = flt(frappe.db.get_value("Sales Invoice", row.sales_invoice, "outstanding_amount"))
		amount = flt(cod_amount) if cod_amount is not None else outstanding
		if amount + 0.01 < outstanding:
			frappe.throw(_("Collect {0} for invoice {1}").format(frappe.format(outstanding, "Currency"), row.sales_invoice))
		if outstanding > 0:
			post_cod(row.sales_invoice, outstanding)
	row.db_set("status", "Delivered")
	refresh_status(so)
	so.reload()
	if so.nir_payment_method == "Cash on Delivery" and so.nir_online_status == "Delivered":
		so.db_set("nir_payment_status", "COD Collected")


def post_cod(invoice, amount):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	settings = get_settings()
	pe = get_payment_entry("Sales Invoice", invoice, party_amount=amount)
	pe.mode_of_payment = settings.cod_mode_of_payment or "Cash"
	pe.reference_no, pe.reference_date = invoice, nowdate()
	account = frappe.db.get_value("Mode of Payment Account", {"parent": pe.mode_of_payment, "company": pe.company}, "default_account")
	if account:
		pe.paid_to = account
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.submit()
	return pe.name


def fulfilment(sales_order, warehouse, statuses):
	so = online_order(sales_order)
	row = next((f for f in so.nir_fulfilments if f.warehouse == warehouse), None)
	if not row or row.status not in statuses:
		frappe.throw(_("{0} is not at a stage where this can be done").format(warehouse))
	return row


# ---- cancel / reject


def close_order(so, status, reason):
	"""Cancel or reject: draft orders just close; confirmed but unbilled orders are cancelled with their transfers."""
	if any(f.sales_invoice and frappe.db.get_value("Sales Invoice", f.sales_invoice, "docstatus") == 1 for f in so.nir_fulfilments):
		frappe.throw(_("Part of this order is already billed; cancel or return the invoices first"))
	paid = so.nir_payment_status == "Paid"
	if so.docstatus == 1:
		for f in so.nir_fulfilments:
			if f.transfer_doctype and frappe.db.get_value(f.transfer_doctype, f.transfer_name, "docstatus") == 1 and f.transfer_doctype == "Material Request":
				mr = frappe.get_doc("Material Request", f.transfer_name)
				if not flt(mr.per_ordered):
					mr.flags.ignore_permissions = True
					mr.cancel()
			elif f.transfer_doctype == "Store Transfer Request":
				frappe.db.set_value("Store Transfer Request", f.transfer_name, "status", "Rejected")
		if so.nir_payment_request:
			pr = frappe.get_doc("Payment Request", so.nir_payment_request)
			if pr.docstatus == 1 and pr.status != "Paid":
				pr.flags.ignore_permissions = True
				pr.cancel()
		if not paid:
			so.flags.ignore_permissions = True
			so.cancel()
		else:
			# the advance stays with the customer until refunded; the order is closed so nothing more is billed
			from erpnext.selling.doctype.sales_order.sales_order import update_status

			update_status("Closed", so.name)
	so.db_set({"nir_online_status": status, "nir_cancel_reason": reason, "nir_payment_status": "Refund Due" if paid else so.nir_payment_status})
