# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""Trip planning: vehicle (own or hired), driver, stops in route sequence, load manifest by tote, trip sheet,
and custody of returnable totes, crates and ice boxes at each store.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from pharmacy.overrides.tote_tracking import log_movement, reset_for_reuse

ACTIVE_TRIP = ("Planned", "Loading", "Departed")


class DispatchTrip(Document):
	def validate(self):
		if self.vehicle_ownership == "Own":
			self.transporter = None
			self.hire_charges = 0
			if self.vehicle:
				self.vehicle_no = self.vehicle_no or frappe.db.get_value("Vehicle", self.vehicle, "license_plate") or self.vehicle
		else:
			self.vehicle = None

	@frappe.whitelist()
	def get_dispatches(self):
		"""Stops and manifest from this route's waves dispatched for the trip date and not on another trip."""
		self.check_permission("write")
		if self.status != "Planned":
			frappe.throw(_("Dispatches can be fetched only while the trip is planned"))

		on_other_trips = set(
			frappe.db.sql_list(
				"""select tt.document_name from `tabDispatch Trip Tote` tt join `tabDispatch Trip` t on t.name = tt.parent
				where t.status in %s and t.name != %s""",
				(ACTIVE_TRIP + ("Completed",), self.name or ""),
			)
		)
		waves = frappe.get_all(
			"Pick Wave", filters={"route": self.route, "wave_date": self.trip_date, "status": "Dispatched"}, pluck="name"
		)
		route_stops = {
			s.store_warehouse: s
			for s in frappe.get_all(
				"Delivery Route Stop", filters={"parent": self.route},
				fields=["sequence", "pharmacy_store", "store_warehouse", "distance_km"],
			)
		}

		self.stops, self.totes = [], []
		per_store = {}
		for wave in waves:
			wave_doc = frappe.get_doc("Pick Wave", wave)
			docs = {d.store_warehouse: d for d in wave_doc.dispatches}
			for t in wave_doc.totes:
				tote = frappe.db.get_value("Tote", t.tote, ["tote_type", "seal_no", "dispatch_doctype", "dispatch_name", "status"], as_dict=True)
				if tote.dispatch_name in on_other_trips or tote.status != "Dispatched":
					continue
				self.append("totes", {"tote": t.tote, "store_warehouse": t.store_warehouse, "tote_type": tote.tote_type,
					"seal_no": tote.seal_no, "document_type": tote.dispatch_doctype, "document_name": tote.dispatch_name})
				store = per_store.setdefault(t.store_warehouse, frappe._dict(totes=0, cold=0, scheduled=0, docs=set()))
				store.totes += 1
				store.cold += tote.tote_type == "Insulated Cold Box"
				store.scheduled += tote.tote_type == "Scheduled Drugs"
				store.docs.add(tote.dispatch_name)
			for store_wh, d in docs.items():
				per_store.setdefault(store_wh, frappe._dict(totes=0, cold=0, scheduled=0, docs=set())).docs.add(d.document_name)

		for store_wh, store in sorted(per_store.items(), key=lambda kv: getattr(route_stops.get(kv[0]), "sequence", 999)):
			stop = route_stops.get(store_wh, frappe._dict())
			self.append("stops", {"sequence": stop.sequence, "store_warehouse": store_wh, "pharmacy_store": stop.pharmacy_store,
				"distance_km": stop.distance_km, "dispatch_documents": "\n".join(sorted(store.docs)),
				"totes": store.totes, "cold_boxes": store.cold, "scheduled_totes": store.scheduled})
		self.save()
		return {"stops": len(self.stops), "totes": len(self.totes)}


def get_trip(trip, statuses):
	doc = frappe.get_doc("Dispatch Trip", trip)
	doc.check_permission("write")
	if doc.status not in statuses:
		frappe.throw(_("Trip {0} is {1}").format(doc.name, doc.status))
	return doc


@frappe.whitelist()
def load_scan(trip: str, tote: str):
	"""Scan each tote onto the vehicle at the dock."""
	doc = get_trip(trip, ("Planned", "Loading"))
	tote = (tote or "").strip().upper()
	row = next((t for t in doc.totes if t.tote == tote), None)
	if not row:
		frappe.throw(_("Tote {0} is not on this trip's manifest").format(tote))
	row.loaded = 1
	doc.status = "Loading"
	doc.save()
	return {"loaded": sum(t.loaded for t in doc.totes), "of": len(doc.totes)}


@frappe.whitelist()
def depart(trip: str):
	doc = get_trip(trip, ("Planned", "Loading"))
	if not doc.totes:
		frappe.throw(_("Nothing on the manifest"))
	missing = [t.tote for t in doc.totes if not t.loaded]
	if missing:
		frappe.throw(_("Scan these totes onto the vehicle first: {0}").format(", ".join(missing)))

	transporter_name = frappe.db.get_value("Supplier", doc.transporter, "supplier_name") if doc.transporter else None
	distances = {s.store_warehouse: s.distance_km for s in doc.stops}
	for row in {(t.document_type, t.document_name, t.store_warehouse) for t in doc.totes}:
		doctype, name, store = row
		# e-way bill transport details (Part B); India Compliance reads them from the document
		values = {"vehicle_no": doc.vehicle_no, "mode_of_transport": "Road", "gst_vehicle_type": "Regular",
			"distance": int(distances.get(store) or 0), "transporter": doc.transporter, "transporter_name": transporter_name,
			"lr_no": doc.name, "lr_date": doc.trip_date}
		meta = frappe.get_meta(doctype)
		frappe.db.set_value(doctype, name, {k: v for k, v in values.items() if meta.has_field(k)})

	for t in doc.totes:
		frappe.db.set_value("Tote", t.tote, {"status": "In Transit", "last_trip": doc.name})
	doc.status = "Departed"
	doc.departure_time = now_datetime()
	doc.save()


@frappe.whitelist()
def deliver_stop(trip: str, stop: str, received_by: str):
	"""Hand over at a store: its totes are now in the store's custody."""
	doc = get_trip(trip, ("Departed",))
	row = next((s for s in doc.stops if s.name == stop), None)
	if not row or row.status == "Delivered":
		frappe.throw(_("Stop already delivered or not on this trip"))
	if not received_by:
		frappe.throw(_("Enter who received the delivery"))

	row.status = "Delivered"
	row.arrived_on = now_datetime()
	row.received_by = received_by
	for t in doc.totes:
		if t.store_warehouse == row.store_warehouse:
			frappe.db.set_value("Tote", t.tote, {"status": "At Store", "holder_store": t.store_warehouse, "issued_on": now_datetime()})
			log_movement(t.tote, "Issued", store=t.store_warehouse, trip=doc.name)
	doc.save()


@frappe.whitelist()
def return_scan(trip: str, tote: str, condition: str = "Good"):
	"""Empty totes, crates and ice boxes collected from stores on the trip."""
	doc = get_trip(trip, ("Departed", "Completed"))
	tote = (tote or "").strip().upper()
	t = frappe.db.get_value("Tote", tote, ["status", "holder_store"], as_dict=True)
	if not t:
		frappe.throw(_("Tote {0} not found").format(tote))
	if t.status not in ("At Store", "Missing"):
		frappe.throw(_("Tote {0} is {1}; only totes at a store can be returned").format(tote, t.status))

	if t.status == "Missing":
		log_movement(tote, "Found", store=t.holder_store, trip=doc.name)
	log_movement(tote, "Returned", store=t.holder_store, trip=doc.name, condition=condition)
	reset_for_reuse(tote)
	if condition == "Damaged":
		frappe.db.set_value("Tote", tote, "status", "Damaged")
	doc.append("returns", {"tote": tote, "from_store": t.holder_store, "condition": condition, "returned_on": now_datetime()})
	doc.save()
	return {"returned": len(doc.returns)}


@frappe.whitelist()
def complete(trip: str):
	doc = get_trip(trip, ("Departed",))
	pending = [s.store_warehouse for s in doc.stops if s.status != "Delivered"]
	if pending:
		frappe.throw(_("Mark these stops delivered first: {0}").format(", ".join(pending)))
	doc.status = "Completed"
	doc.return_time = now_datetime()
	doc.save()
