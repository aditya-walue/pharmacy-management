# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Shipments on their way to stores, with trip, vehicle and expected arrival (ST-01)."""

import frappe
from frappe import _
from frappe.utils import flt

from pharmacy.overrides.store_transfer import get_shipments, get_trip_info


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = []
	for s in get_shipments(filters.store):
		trip = get_trip_info(s.name, s.store)
		qty_field = "transfer_qty" if s.doctype == "Stock Entry" else "stock_qty"
		child = "Stock Entry Detail" if s.doctype == "Stock Entry" else "Sales Invoice Item"
		lines = frappe.get_all(child, filters={"parent": s.name}, fields=[f"sum({qty_field}) as qty", "count(*) as n"])[0]
		status = "Delivered" if trip.delivered else ("On Trip" if trip.trip_status == "Departed" else "At DC")
		data.append({
			"store": s.store, "document_type": s.doctype, "shipment": s.name, "source": "Store Transfer" if s.transfer else "DC",
			"dispatched_on": s.posting, "status": status, "trip": trip.trip, "vehicle_no": trip.vehicle_no, "driver": trip.driver,
			"eta": trip.eta, "delivered_on": trip.delivered_on,
			"totes": frappe.db.count("Tote", {"dispatch_name": s.name}), "lines": lines.n, "qty": flt(lines.qty),
		})
	return columns(), sorted(data, key=lambda r: (r["store"] or "", str(r["eta"] or r["dispatched_on"])))


def columns():
	return [
		{"fieldname": "store", "label": _("Store"), "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "eta", "label": _("Expected Arrival"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "document_type", "label": _("Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "shipment", "label": _("Shipment"), "fieldtype": "Dynamic Link", "options": "document_type", "width": 160},
		{"fieldname": "source", "label": _("From"), "fieldtype": "Data", "width": 110},
		{"fieldname": "dispatched_on", "label": _("Dispatched"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "trip", "label": _("Trip"), "fieldtype": "Link", "options": "Dispatch Trip", "width": 130},
		{"fieldname": "vehicle_no", "label": _("Vehicle"), "fieldtype": "Data", "width": 100},
		{"fieldname": "driver", "label": _("Driver"), "fieldtype": "Data", "width": 120},
		{"fieldname": "totes", "label": _("Totes"), "fieldtype": "Int", "width": 60},
		{"fieldname": "lines", "label": _("Lines"), "fieldtype": "Int", "width": 60},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "delivered_on", "label": _("Delivered"), "fieldtype": "Datetime", "width": 150},
	]
