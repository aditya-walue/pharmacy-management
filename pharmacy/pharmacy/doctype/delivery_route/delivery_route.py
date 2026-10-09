# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DeliveryRoute(Document):
	def validate(self):
		sequences = [row.sequence for row in self.stops]
		if len(sequences) != len(set(sequences)):
			frappe.throw(_("Each stop needs its own sequence number"))
		stores = [row.pharmacy_store for row in self.stops]
		if len(stores) != len(set(stores)):
			frappe.throw(_("A store can appear only once on a route"))
		self.stops.sort(key=lambda row: row.sequence)
		for idx, row in enumerate(self.stops, start=1):
			row.idx = idx

		if self.active:
			clash = frappe.db.sql(
				"""select stop.pharmacy_store, route.name from `tabDelivery Route Stop` stop
				join `tabDelivery Route` route on route.name = stop.parent
				where route.active = 1 and route.name != %s and stop.pharmacy_store in %s limit 1""",
				(self.name or "", tuple(stores) or ("",)),
			)
			if clash:
				frappe.throw(_("Store {0} is already on active route {1}").format(*clash[0]))

	def on_update(self):
		# Pharmacy Store keeps its route as text; keep it in step with the route master
		for row in self.stops:
			values = {"route": self.route_name}
			if not frappe.db.get_value("Pharmacy Store", row.pharmacy_store, "serving_warehouse"):
				values["serving_warehouse"] = self.dc
			frappe.db.set_value("Pharmacy Store", row.pharmacy_store, values)

	@frappe.whitelist()
	def get_route_day(self, date: str | None = None):
		"""Stores in sequence with items due on the date: each is served on every day it has items due."""
		from pharmacy.pharmacy.doctype.pick_wave.pick_wave import get_pending_lines

		date = date or frappe.utils.today()
		day = []
		for row in self.stops:
			due = frappe.db.sql(
				"""select distinct mr.name from `tabMaterial Request` mr
				join `tabMaterial Request Item` mri on mri.parent = mr.name
				where mr.docstatus = 1 and mr.material_request_type = 'Material Transfer'
					and mr.status not in ('Stopped', 'Cancelled', 'Transferred')
					and mri.warehouse = %s and mri.schedule_date <= %s""",
				(row.store_warehouse, date),
				pluck=True,
			)
			lines = sum(len(get_pending_lines(mr, None)) for mr in due)
			if lines:
				day.append({"sequence": row.sequence, "store": row.pharmacy_store, "indents": len(due), "lines": lines})
		return day
