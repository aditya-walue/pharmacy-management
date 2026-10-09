# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

"""DC outbound: store indents grouped into pick waves, FEFO allocation, handheld zone picking into totes,
short-pick handling, and dispatch on a delivery challan or tax invoice.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, today
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.controlled_drugs import CONTROLLED_CATEGORIES, post
from pharmacy.overrides.inventory import enrich, get_batch_stock
from pharmacy.overrides.shelf_life import get_shelf_life_threshold
from pharmacy.overrides.stock_hold import find_hold, get_active_holds
from pharmacy.overrides.warehouse_layout import RECEIVING_ZONE, get_layout
from pharmacy.pharmacy.substitutes import get_substitutes

DEFAULT_MAX_BATCHES = 2
# a later batch may be preferred over the earliest if it covers the line alone and expires within this many days of it
SINGLE_BATCH_WINDOW_DAYS = 30
OPEN_WAVE_STATUSES = ("Draft", "Allocated", "Picking", "Picked")
TOTE_FOR = {"cold": ("Insulated Cold Box",), "scheduled": ("Scheduled Drugs",), "regular": ("Standard", "Crate")}


class PickWave(Document):
	def validate(self):
		if not self.dispatch_time and self.route:
			self.dispatch_time = frappe.db.get_value("Delivery Route", self.route, "dispatch_time")
		if self.status in ("Dispatched", "Cancelled"):
			return
		if not self.items:
			self.status = "Draft"
		elif not any(flt(row.picked_qty) for row in self.items):
			self.status = "Allocated"
		elif all(row.status in ("Picked", "Short") for row in self.items):
			self.status = "Picked"
		else:
			self.status = "Picking"

	@frappe.whitelist()
	def get_indents(self):
		"""Submitted, due store indents for stores on this route."""
		self.check_permission("write")
		if frappe.db.get_value("Delivery Route", self.route, "dc") != self.source_warehouse:
			frappe.throw(_("Route {0} is not served from {1}").format(self.route, self.source_warehouse))
		by_warehouse = {
			s.store_warehouse: s.pharmacy_store
			for s in frappe.get_all(
				"Delivery Route Stop", filters={"parent": self.route}, fields=["pharmacy_store", "store_warehouse"]
			)
			if s.store_warehouse
		}
		if not by_warehouse:
			frappe.throw(_("Route {0} has no stores").format(self.route))

		taken = set(get_indents_in_open_waves(exclude=self.name))
		indents = frappe.db.sql(
			"""select distinct mr.name, mri.warehouse from `tabMaterial Request` mr
			join `tabMaterial Request Item` mri on mri.parent = mr.name
			where mr.docstatus = 1 and mr.material_request_type = 'Material Transfer' and mr.company = %(company)s
				and mr.status not in ('Stopped', 'Cancelled', 'Transferred') and mri.warehouse in %(stores)s
				and mri.schedule_date <= %(date)s""",
			{"company": self.company, "stores": tuple(by_warehouse), "date": self.wave_date},
			as_dict=True,
		)
		self.indents = []
		for indent in indents:
			if indent.name not in taken:
				self.append(
					"indents",
					{"material_request": indent.name, "store_warehouse": indent.warehouse, "pharmacy_store": by_warehouse[indent.warehouse]},
				)
		self.save()
		return len(self.indents)

	@frappe.whitelist()
	def allocate(self):
		"""FEFO allocation of every pending indent line to DC bins and batches."""
		self.check_permission("write")
		if self.status not in ("Draft", "Allocated"):
			frappe.throw(_("Allocation can be redone only before picking starts"))

		self.items = []
		context = AllocationContext(self)
		for indent in self.indents:
			for line in get_pending_lines(indent.material_request, self.name):
				allocate_line(self, context, line, indent)
		self.save()
		return len(self.items)


class AllocationContext:
	"""Pickable stock in the DC, less what other open waves have already allocated."""

	def __init__(self, wave):
		layout = get_layout(wave.company)
		site = layout[wave.source_warehouse].site
		self.layout = layout
		self.bins = [
			w.name
			for w in layout.values()
			if w.site == site and not w.is_group and not w.disabled and not w.nir_non_sellable and w.zone_type != RECEIVING_ZONE
		]
		self.pick_faces = set(frappe.get_all("Pick Face", filters={"disabled": 0}, pluck="warehouse"))
		self.reserved = get_allocated_elsewhere(wave.name)
		self.max_batches = cint(frappe.db.get_single_value("Stock Settings", "nir_max_batches_per_line")) or DEFAULT_MAX_BATCHES

	def stock_for(self, item_code):
		if not self.bins:
			return []
		holds = get_active_holds([item_code])
		rows = []
		for r in enrich(get_batch_stock(warehouses=self.bins, item_codes=[item_code])):
			free = flt(r.qty) - flt(self.reserved.get((r.warehouse, r.batch_no or "")))
			if free > 0 and not find_hold(holds, item_code, [r.batch_no] if r.batch_no else [], r.warehouse):
				r.free = free
				rows.append(r)
		return rows

	def take(self, warehouse, batch_no, qty):
		key = (warehouse, batch_no or "")
		self.reserved[key] = flt(self.reserved.get(key)) + qty


def allocate_line(wave, context, line, indent, substitute_for=None):
	item = frappe.get_cached_value("Item", line.item_code, ["nir_storage_condition", "nir_regulatory_category"], as_dict=True)
	min_days = get_shelf_life_threshold(line.item_code, "min_days_store_dispatch") or 0
	stock = [
		r for r in context.stock_for(line.item_code)
		if not r.expiry_date or (getdate(r.expiry_date) - getdate(wave.wave_date)).days >= min_days
	]
	plan = choose_batches(stock, line.qty, context)
	base = {
		"store_warehouse": indent.store_warehouse,
		"item_code": line.item_code,
		"material_request": indent.material_request,
		"material_request_item": line.name,
		"stock_uom": line.stock_uom,
		"is_cold_chain": int(item.nir_storage_condition == "2-8C"),
		"is_scheduled": int(item.nir_regulatory_category in CONTROLLED_CATEGORIES),
		"substitute_for": substitute_for,
	}
	allocated = 0
	for r, qty in plan:
		context.take(r.warehouse, r.batch_no, qty)
		allocated += qty
		wave.append(
			"items",
			{**base, "batch_no": r.batch_no, "source_bin": r.warehouse, "zone": context.layout[r.warehouse].zone_type,
			 "qty": qty, "status": "Pending"},
		)
	if flt(line.qty) - allocated > 0.0001:
		wave.append("items", {**base, "qty": 0, "short_qty": flt(line.qty) - allocated, "status": "Short"})


def choose_batches(stock, needed, context):
	"""[(stock row, qty)] — earliest expiry first, few batches, pick faces before reserve within a batch."""
	batches = {}
	for r in stock:
		batches.setdefault(r.batch_no or "", []).append(r)
	order = sorted(
		batches,
		key=lambda b: getdate(batches[b][0].expiry_date) if batches[b][0].expiry_date else getdate("9999-12-31"),
	)
	total = {b: sum(r.free for r in batches[b]) for b in order}

	chosen = []
	if order and total[order[0]] < needed:
		# prefer one slightly later batch that covers the whole line over splitting
		first_expiry = batches[order[0]][0].expiry_date
		for b in order[1:]:
			expiry = batches[b][0].expiry_date
			within_window = not first_expiry or not expiry or (getdate(expiry) - getdate(first_expiry)).days <= SINGLE_BATCH_WINDOW_DAYS
			if total[b] >= needed and within_window:
				chosen = [b]
				break
	if not chosen:
		chosen = order[: context.max_batches]

	plan, remaining = [], flt(needed)
	for b in chosen:
		rows = sorted(batches[b], key=lambda r: (r.warehouse not in context.pick_faces, -r.free))
		for r in rows:
			if remaining <= 0:
				break
			qty = min(remaining, r.free)
			plan.append((r, qty))
			remaining -= qty
	return plan


def get_pending_lines(material_request, current_wave):
	"""Indent lines with qty not yet dispatched, cancelled, or allocated in another open wave.

	Waves are the record of what left: invoice-route transfers never update the indent's ordered qty.
	"""
	lines = frappe.get_all(
		"Material Request Item",
		filters={"parent": material_request},
		fields=["name", "item_code", "stock_qty", "ordered_qty", "conversion_factor", "stock_uom", "nir_cancelled_qty"],
		order_by="idx asc",
	)
	in_other_waves, dispatched = {}, {}
	for r in frappe.db.sql(
		"""select pwi.material_request_item, pw.status, sum(pwi.qty) as allocated, sum(pwi.picked_qty) as picked
		from `tabPick Wave Item` pwi join `tabPick Wave` pw on pw.name = pwi.parent
		where pw.name != %s and pwi.material_request = %s and pw.status != 'Cancelled'
		group by pwi.material_request_item, pw.status""",
		(current_wave or "", material_request),
		as_dict=True,
	):
		if r.status == "Dispatched":
			dispatched[r.material_request_item] = flt(dispatched.get(r.material_request_item)) + flt(r.picked)
		else:
			in_other_waves[r.material_request_item] = flt(in_other_waves.get(r.material_request_item)) + flt(r.allocated)

	pending = []
	for line in lines:
		# ordered_qty is already in stock units (sum of transfer_qty)
		done = max(flt(line.ordered_qty), flt(dispatched.get(line.name)))
		line.qty = flt(line.stock_qty) - done - flt(line.nir_cancelled_qty) - flt(in_other_waves.get(line.name))
		if line.qty > 0.0001:
			pending.append(line)
	return pending


def get_allocated_elsewhere(current_wave):
	"""Bin and batch qty promised to other open waves."""
	return {
		(r.source_bin, r.batch_no or ""): flt(r.qty)
		for r in frappe.db.sql(
			"""select pwi.source_bin, pwi.batch_no, sum(pwi.qty) as qty from `tabPick Wave Item` pwi
			join `tabPick Wave` pw on pw.name = pwi.parent
			where pw.status in %s and pw.name != %s and pwi.source_bin is not null
			group by pwi.source_bin, pwi.batch_no""",
			(OPEN_WAVE_STATUSES, current_wave or ""),
			as_dict=True,
		)
	}


def get_indents_in_open_waves(exclude=None):
	return frappe.db.sql_list(
		"""select distinct pwi.material_request from `tabPick Wave Indent` pwi
		join `tabPick Wave` pw on pw.name = pwi.parent
		where pw.status in %s and pw.name != %s""",
		(OPEN_WAVE_STATUSES, exclude or ""),
	)


@frappe.whitelist()
def create_waves(company: str, source_warehouse: str, wave_date: str | None = None):
	"""One wave per route with stores served from this DC, each with its due indents allocated."""
	frappe.has_permission("Pick Wave", "create", throw=True)
	routes = frappe.get_all("Delivery Route", filters={"dc": source_warehouse, "active": 1}, pluck="name", order_by="dispatch_time asc")
	created = []
	for route in routes:
		wave = frappe.get_doc(
			{"doctype": "Pick Wave", "company": company, "source_warehouse": source_warehouse, "route": route,
			 "wave_date": wave_date or today()}
		).insert()
		if wave.get_indents():
			wave.allocate()
			created.append(wave.name)
		else:
			wave.delete()
	return created


# Handheld picking


@frappe.whitelist()
def pick_scan(wave: str, bin_code: str, code: str, qty: float, tote: str):
	"""Scan bin, then batch (or item), qty and tote. Wrong bin, batch or tote is refused."""
	doc = frappe.get_doc("Pick Wave", wave)
	doc.check_permission("write")
	if doc.status not in ("Allocated", "Picking"):
		frappe.throw(_("{0} is not open for picking").format(doc.name))

	bin_code, code, tote = (bin_code or "").strip(), (code or "").strip(), (tote or "").strip()
	item_code = frappe.db.get_value("Batch", code, "item") or frappe.db.get_value("Item Barcode", {"barcode": code}, "parent") or code
	row = next(
		(r for r in doc.items
		 if r.status == "Pending" and r.source_bin == bin_code and r.item_code == item_code and (not r.batch_no or r.batch_no == code)),
		None,
	)
	if not row:
		frappe.throw(_("Nothing to pick for {0} from bin {1} on this wave. Check the bin and batch.").format(code, bin_code))

	qty = flt(qty)
	if qty <= 0 or flt(row.picked_qty) + qty > flt(row.qty) + 0.0001:
		frappe.throw(_("Pick at most {0} more").format(flt(row.qty) - flt(row.picked_qty)))

	check_tote(doc, row, tote)
	row.picked_qty = flt(row.picked_qty) + qty
	row.tote = tote
	row.picked_by = frappe.session.user
	if row.picked_qty >= flt(row.qty) - 0.0001:
		row.status = "Picked"
	if not any(t.tote == tote for t in doc.totes):
		doc.append("totes", {"tote": tote, "store_warehouse": row.store_warehouse, "tote_type": frappe.db.get_value("Tote", tote, "tote_type")})
	frappe.db.set_value("Tote", tote, {"status": "In Use", "current_wave": doc.name, "store_warehouse": row.store_warehouse})
	doc.save()
	return {"item_code": row.item_code, "picked": row.picked_qty, "of": row.qty, "line_done": row.status == "Picked"}


def check_tote(wave, row, tote):
	t = frappe.db.get_value("Tote", tote, ["tote_type", "status", "current_wave", "store_warehouse"], as_dict=True)
	if not t:
		frappe.throw(_("Tote {0} not found").format(tote))
	if t.status not in ("Available", "In Use"):
		frappe.throw(_("Tote {0} is {1}, not available for picking").format(tote, t.status))
	if t.status == "In Use" and (t.current_wave != wave.name or t.store_warehouse != row.store_warehouse):
		frappe.throw(_("Tote {0} is in use for another store or wave").format(tote))

	kind = "scheduled" if row.is_scheduled else "cold" if row.is_cold_chain else "regular"
	if t.tote_type not in TOTE_FOR[kind]:
		frappe.throw(
			_("{0} must go in a {1}; {2} is a {3}").format(row.item_code, " / ".join(TOTE_FOR[kind]), tote, t.tote_type),
			title=_("Wrong tote"),
		)


@frappe.whitelist()
def mark_short(wave: str, row_name: str):
	"""Picker could not find the rest of the line."""
	doc = frappe.get_doc("Pick Wave", wave)
	doc.check_permission("write")
	row = next((r for r in doc.items if r.name == row_name), None)
	if not row or row.status != "Pending":
		frappe.throw(_("Only a pending line can be marked short"))
	row.short_qty = flt(row.qty) - flt(row.picked_qty)
	row.status = "Short"
	doc.save()


@frappe.whitelist()
def resolve_short(wave: str, row_name: str, action: str):
	"""Backorder (stays on the indent), cancel the qty on the indent, or substitute under the agreed rules."""
	doc = frappe.get_doc("Pick Wave", wave)
	doc.check_permission("write")
	row = next((r for r in doc.items if r.name == row_name), None)
	if not row or row.status != "Short" or row.short_action:
		frappe.throw(_("This line has no open shortage"))
	if action not in ("Backorder", "Substitute", "Cancel"):
		frappe.throw(_("Invalid action"))

	if action == "Substitute":
		substitute = find_substitute(row)
		context = AllocationContext(doc)
		indent = frappe._dict(material_request=row.material_request, store_warehouse=row.store_warehouse)
		line = frappe._dict(name=row.material_request_item, item_code=substitute, qty=row.short_qty,
			stock_uom=frappe.get_cached_value("Item", substitute, "stock_uom"))
		allocate_line(doc, context, line, indent, substitute_for=row.item_code)
	elif action == "Cancel":
		cancelled = flt(frappe.db.get_value("Material Request Item", row.material_request_item, "nir_cancelled_qty"))
		frappe.db.set_value("Material Request Item", row.material_request_item, "nir_cancelled_qty", cancelled + flt(row.short_qty))

	row.short_action = action
	doc.save()
	frappe.get_doc("Material Request", row.material_request).add_comment(
		"Comment", _("{0} {1} short on wave {2}: {3}").format(row.short_qty, row.item_code, doc.name, action.lower())
	)


def find_substitute(row):
	store = frappe.db.get_value("Pharmacy Store", {"warehouse": row.store_warehouse}, ["name", "nir_allow_substitution"], as_dict=True)
	if not store or not store.nir_allow_substitution:
		frappe.throw(_("Store {0} does not accept substitutes").format(row.store_warehouse))
	if row.is_scheduled:
		frappe.throw(_("Schedule X and NDPS items are never substituted"))

	original = frappe.get_cached_value("Item", row.item_code, ["nir_dosage_form"], as_dict=True)
	original_mrp = latest_mrp(row.item_code)
	for candidate in get_substitutes(row.item_code):
		category = frappe.get_cached_value("Item", candidate.item_code, "nir_regulatory_category")
		if category in CONTROLLED_CATEGORIES or candidate.nir_dosage_form != original.nir_dosage_form:
			continue
		mrp = latest_mrp(candidate.item_code)
		if original_mrp and mrp and mrp > original_mrp:
			continue
		return candidate.item_code
	frappe.throw(_("No substitute for {0} meets the agreed rules").format(row.item_code))


def latest_mrp(item_code):
	return flt(frappe.db.get_value("Batch", {"item": item_code, "nir_mrp": (">", 0)}, "nir_mrp", order_by="creation desc"))


@frappe.whitelist()
def seal_tote(tote: str, seal_no: str, ice_packs: int | None = None, temperature: str | None = None):
	frappe.has_permission("Tote", "write", throw=True)
	t = frappe.get_doc("Tote", tote)
	if t.status != "In Use":
		frappe.throw(_("Only a tote in use can be sealed"))
	if not seal_no:
		frappe.throw(_("Enter the seal number"))
	if t.tote_type == "Insulated Cold Box" and (cint(ice_packs) <= 0 or not temperature):
		frappe.throw(_("Record the ice packs and the temperature at packing for a cold box"))

	t.update({"status": "Sealed", "seal_no": seal_no, "sealed_by": frappe.session.user, "sealed_on": now_datetime(),
		"ice_packs": cint(ice_packs), "packed_temperature": temperature})
	t.save(ignore_permissions=True)
	if t.current_wave:
		frappe.db.set_value("Pick Wave Tote", {"parent": t.current_wave, "tote": tote}, "seal_no", seal_no)


# Dispatch


@frappe.whitelist()
def dispatch(wave: str):
	"""Per store: a delivery challan (same GSTIN) or tax invoice (other GSTIN or company); scheduled drugs separately."""
	doc = frappe.get_doc("Pick Wave", wave)
	doc.check_permission("write")
	if doc.status != "Picked":
		frappe.throw(_("Finish picking (or mark lines short) before dispatch"))
	unresolved = [f"#{r.idx} {r.item_code}" for r in doc.items if r.status == "Short" and not r.short_action]
	if unresolved:
		frappe.throw(_("Choose Backorder, Substitute or Cancel for short lines: {0}").format(", ".join(unresolved)))
	unsealed = [t.tote for t in doc.totes if frappe.db.get_value("Tote", t.tote, "status") != "Sealed"]
	if unsealed:
		frappe.throw(_("Seal these totes first: {0}").format(", ".join(unsealed)))

	for store in sorted({r.store_warehouse for r in doc.items}):
		rows = [r for r in doc.items if r.store_warehouse == store and flt(r.picked_qty)]
		for scheduled in (0, 1):
			part = [r for r in rows if r.is_scheduled == scheduled]
			if part:
				doctype, name = make_dispatch_document(doc, store, part, scheduled)
				doc.append("dispatches", {"store_warehouse": store, "document_type": doctype, "document_name": name, "scheduled_drugs": scheduled})
				for tote in {r.tote for r in part}:
					frappe.db.set_value("Tote", tote, {"status": "Dispatched", "dispatch_doctype": doctype, "dispatch_name": name})
		notify_store(doc, store)

	doc.status = "Dispatched"
	doc.save()
	return [d.document_name for d in doc.dispatches]


def needs_invoice(doc, store):
	from pharmacy.overrides.store_transfer import needs_invoice as invoice_needed

	return invoice_needed(doc.company, doc.source_warehouse, store)


def make_dispatch_document(doc, store, rows, scheduled):
	totes = ", ".join(
		f"{t.tote} (seal {t.seal_no or '-'})" for t in doc.totes if t.tote in {r.tote for r in rows}
	)
	if needs_invoice(doc, store):
		document = make_invoice(doc, store, rows, totes)
	else:
		document = make_challan(doc, store, rows, totes)
	if scheduled:
		for row in document.items:
			category = frappe.get_cached_value("Item", row.item_code, "nir_regulatory_category")
			post(document, frappe._dict(row.as_dict(), warehouse=row.get("s_warehouse") or row.get("warehouse")),
				category, "Transfer", qty_out=flt(row.get("transfer_qty") or row.get("stock_qty")))
	return document.doctype, document.name


def make_challan(doc, store, rows, totes):
	transit = frappe.db.get_value("Company", doc.company, "default_in_transit_warehouse") or frappe.db.get_value(
		"Warehouse", {"company": doc.company, "warehouse_type": "Transit", "is_group": 0}
	)
	if not transit:
		frappe.throw(_("Set a Default In-Transit Warehouse on company {0}").format(doc.company))
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"company": doc.company,
			"add_to_transit": 1,
			"nir_pick_wave": doc.name,
			"nir_destination_store": store,
			"nir_totes": totes,
			"remarks": _("Delivery challan for {0}, wave {1}").format(store, doc.name),
			"items": [
				{
					"item_code": r.item_code,
					"qty": flt(r.picked_qty),
					"s_warehouse": r.source_bin,
					"t_warehouse": transit,
					"batch_no": r.batch_no,
					"use_serial_batch_fields": 1 if r.batch_no else 0,
					# a substitute is a different item from the indent line, so it can't carry the link
					"material_request": None if r.substitute_for else r.material_request,
					"material_request_item": None if r.substitute_for else r.material_request_item,
				}
				for r in rows
			],
		}
	)
	entry.insert()
	entry.submit()
	return entry


def make_invoice(doc, store, rows, totes):
	customer = frappe.db.get_value("Pharmacy Store", {"warehouse": store}, "nir_internal_customer")
	if not customer:
		frappe.throw(_("Set the Internal Customer on the Pharmacy Store for {0} to invoice its transfers").format(store))
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": doc.company,
			"customer": customer,
			"update_stock": 1,
			"set_target_warehouse": store,
			"nir_pick_wave": doc.name,
			"nir_totes": totes,
			"remarks": _("Stock transfer invoice for {0}, wave {1}").format(store, doc.name),
			"items": [
				{
					"item_code": r.item_code,
					"qty": flt(r.picked_qty),
					"warehouse": r.source_bin,
					"target_warehouse": store,
					"batch_no": r.batch_no,
					"use_serial_batch_fields": 1 if r.batch_no else 0,
				}
				for r in rows
			],
		}
	)
	invoice.insert()
	invoice.submit()
	return invoice


def notify_store(doc, store):
	shorts = [r for r in doc.items if r.store_warehouse == store and r.status == "Short"]
	subject = _("Wave {0} dispatched to {1}").format(doc.name, store)
	if shorts:
		subject += _(" — {0} short lines: {1}").format(
			len(shorts), "; ".join(f"{r.item_code} {flt(r.short_qty)} {r.short_action}" for r in shorts)
		)
	for user in get_users_with_role("Store Pharmacist"):
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Pick Wave",
			 "document_name": doc.name, "subject": subject[:140]}
		).insert(ignore_permissions=True)
