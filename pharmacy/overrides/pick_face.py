"""Pick faces topped up from reserve storage (WH-02): hourly draft transfers, earliest expiry first."""

import frappe
from frappe import _
from frappe.utils import flt, getdate
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.inventory import enrich, get_batch_stock
from pharmacy.overrides.stock_hold import find_hold, get_active_holds
from pharmacy.overrides.warehouse_layout import get_layout

TOPUP_ROLES = ("Picker Packer", "Warehouse Manager")


def create_topups():
	faces = frappe.get_all(
		"Pick Face", filters={"disabled": 0}, fields=["name", "company", "warehouse", "item_code", "min_qty", "max_qty"]
	)
	if not faces:
		return

	open_topups = set(
		frappe.get_all("Stock Entry", filters={"docstatus": 0, "nir_pick_face": ("is", "set")}, pluck="nir_pick_face")
	)
	pick_bins = {f.warehouse for f in faces}
	layouts = {}
	created = []
	for face in faces:
		if face.name in open_topups:
			continue
		on_hand = flt(frappe.db.get_value("Bin", {"warehouse": face.warehouse, "item_code": face.item_code}, "actual_qty"))
		if on_hand >= flt(face.min_qty):
			continue

		layout = layouts.setdefault(face.company, get_layout(face.company))
		lines = plan_topup(face, flt(face.max_qty) - on_hand, layout, pick_bins)
		if lines:
			created.append(make_topup(face, lines))

	if created:
		users = {u for role in TOPUP_ROLES for u in get_users_with_role(role)}
		for user in users:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"document_type": "Stock Entry",
					"document_name": created[0],
					"subject": _("{0} pick-face top-ups to move: {1}").format(len(created), ", ".join(created)),
				}
			).insert(ignore_permissions=True)


def plan_topup(face, needed, layout, pick_bins):
	"""Reserve stock in the same DC, earliest expiry first; never from pick faces, holding zones or held stock."""
	site = layout[face.warehouse].site
	reserve = [
		w.name
		for w in layout.values()
		if w.site == site and not w.is_group and not w.nir_non_sellable and w.name not in pick_bins
	]
	if not reserve:
		return []

	holds = get_active_holds([face.item_code])
	stock = [
		r
		for r in enrich(get_batch_stock(company=face.company, warehouses=reserve, item_codes=[face.item_code]))
		if flt(r.qty) > 0 and not find_hold(holds, r.item_code, [r.batch_no] if r.batch_no else [], r.warehouse)
	]
	stock.sort(key=lambda r: (getdate(r.expiry_date) if r.expiry_date else getdate("9999-12-31"), r.warehouse))

	lines = []
	for r in stock:
		if needed <= 0:
			break
		take = min(needed, flt(r.qty))
		lines.append({"warehouse": r.warehouse, "batch_no": r.batch_no, "qty": take})
		needed -= take
	return lines


def make_topup(face, lines):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"company": face.company,
			"nir_pick_face": face.name,
			"remarks": _("Pick-face top-up for {0} at {1}").format(face.item_code, face.warehouse),
			"items": [
				{
					"item_code": face.item_code,
					"qty": line["qty"],
					"s_warehouse": line["warehouse"],
					"t_warehouse": face.warehouse,
					"batch_no": line["batch_no"],
					"use_serial_batch_fields": 1 if line["batch_no"] else 0,
				}
				for line in lines
			],
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Pick Face", face.name, "last_topup", entry.name, update_modified=False)
	return entry.name
