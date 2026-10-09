"""Shared by DC dispatch and store-to-store transfers: challan vs tax invoice, shipments, delivery times."""

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, get_datetime

from pharmacy.overrides.warehouse_layout import get_layout


def get_gstin(warehouse):
	"""A store's GSTIN from its Pharmacy Store; a DC's from its site warehouse."""
	gstin = frappe.db.get_value("Pharmacy Store", {"warehouse": warehouse}, "gstin")
	if not gstin:
		company = frappe.db.get_value("Warehouse", warehouse, "company")
		site = get_layout(company).get(warehouse, frappe._dict()).site
		gstin = frappe.db.get_value("Warehouse", site or warehouse, "nir_gstin")
	return (gstin or "").strip().upper()


def needs_invoice(company, from_warehouse, to_warehouse):
	"""GST treats each GSTIN as a separate person: another company or GSTIN needs a tax invoice, else a challan."""
	if frappe.db.get_value("Warehouse", to_warehouse, "company") != company:
		return True
	source, target = get_gstin(from_warehouse), get_gstin(to_warehouse)
	return bool(source and target and source != target)


def get_transit_warehouse(company):
	transit = frappe.db.get_value("Company", company, "default_in_transit_warehouse") or frappe.db.get_value(
		"Warehouse", {"company": company, "warehouse_type": "Transit", "is_group": 0}
	)
	if not transit:
		frappe.throw(_("Set a Default In-Transit Warehouse on company {0}").format(company))
	return transit


def make_challan(company, store, rows, remarks, **links):
	"""Delivery challan: transfer into transit, received at the store later."""
	transit = get_transit_warehouse(company)
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"company": company,
			"add_to_transit": 1,
			"nir_destination_store": store,
			"remarks": remarks,
			"items": [
				{
					"item_code": r["item_code"],
					"qty": flt(r["qty"]),
					"s_warehouse": r["s_warehouse"],
					"t_warehouse": transit,
					"batch_no": r.get("batch_no"),
					"use_serial_batch_fields": 1 if r.get("batch_no") else 0,
					"material_request": r.get("material_request"),
					"material_request_item": r.get("material_request_item"),
				}
				for r in rows
			],
			**links,
		}
	)
	entry.insert()
	entry.submit()
	return entry


def make_invoice(company, store, rows, remarks, **links):
	"""Tax invoice to the store's internal customer; e-invoice and e-way bill via India Compliance."""
	customer = frappe.db.get_value("Pharmacy Store", {"warehouse": store}, "nir_internal_customer")
	if not customer:
		frappe.throw(_("Set the Internal Customer on the Pharmacy Store for {0} to invoice its transfers").format(store))
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": customer,
			"update_stock": 1,
			"set_target_warehouse": store,
			"remarks": remarks,
			"items": [
				{
					"item_code": r["item_code"],
					"qty": flt(r["qty"]),
					"warehouse": r["s_warehouse"],
					"target_warehouse": store,
					"batch_no": r.get("batch_no"),
					"use_serial_batch_fields": 1 if r.get("batch_no") else 0,
				}
				for r in rows
			],
			**links,
		}
	)
	invoice.insert()
	invoice.submit()
	return invoice


def get_shipments(store=None):
	"""Challans and invoices on their way to stores and not yet received."""
	received = set(
		frappe.get_all("Store Receipt", filters={"docstatus": 1}, pluck="dispatch_name")
	)
	filters = {"docstatus": 1, "add_to_transit": 1, "nir_destination_store": ("is", "set"), "per_transferred": ("<", 100)}
	if store:
		filters["nir_destination_store"] = store
	shipments = [
		frappe._dict(doctype="Stock Entry", name=s.name, store=s.nir_destination_store, company=s.company,
			posting=get_datetime(f"{s.posting_date} {s.posting_time}"), wave=s.nir_pick_wave, transfer=s.nir_store_transfer)
		for s in frappe.get_all(
			"Stock Entry", filters=filters,
			fields=["name", "nir_destination_store", "company", "posting_date", "posting_time", "nir_pick_wave", "nir_store_transfer"],
		)
	]
	inv_filters = {"docstatus": 1, "is_return": 0, "set_target_warehouse": ("is", "set")}
	if store:
		inv_filters["set_target_warehouse"] = store
	shipments += [
		frappe._dict(doctype="Sales Invoice", name=s.name, store=s.set_target_warehouse, company=s.company,
			posting=get_datetime(f"{s.posting_date} {s.posting_time}"), wave=s.nir_pick_wave, transfer=s.nir_store_transfer)
		for s in frappe.get_all(
			"Sales Invoice", filters=inv_filters,
			fields=["name", "set_target_warehouse", "company", "posting_date", "posting_time", "nir_pick_wave", "nir_store_transfer"],
		)
		if s.nir_pick_wave or s.nir_store_transfer
	]
	return [s for s in shipments if s.name not in received]


def get_trip_info(document_name, store):
	"""Trip, stop status, delivery time and ETA for a shipment, if it is on a trip."""
	trip = frappe.db.sql(
		"""select t.name, t.status, t.departure_time, t.vehicle_no, t.driver_name, t.trip_date, t.route
		from `tabDispatch Trip Tote` tt join `tabDispatch Trip` t on t.name = tt.parent
		where tt.document_name = %s and t.status != 'Cancelled' order by t.creation desc limit 1""",
		document_name,
		as_dict=True,
	)
	if not trip:
		return frappe._dict()
	trip = trip[0]
	stop = frappe.db.get_value(
		"Dispatch Trip Stop", {"parent": trip.name, "store_warehouse": store}, ["status", "arrived_on"], as_dict=True
	) or frappe._dict()
	minutes = frappe.db.get_value("Delivery Route Stop", {"parent": trip.route, "store_warehouse": store}, "minutes_from_dc") or 0
	start = trip.departure_time
	if not start:
		dispatch_time = frappe.db.get_value("Delivery Route", trip.route, "dispatch_time")
		start = get_datetime(f"{trip.trip_date} {dispatch_time}") if dispatch_time else None
	return frappe._dict(
		trip=trip.name, trip_status=trip.status, vehicle_no=trip.vehicle_no, driver=trip.driver_name,
		delivered=stop.status == "Delivered", delivered_on=stop.arrived_on,
		eta=add_to_date(start, minutes=minutes) if start else None,
	)
