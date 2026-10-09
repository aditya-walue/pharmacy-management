"""Pick and pack for online orders, with ERPNext Pick Lists.

Sales Order → Create → Pick List (earliest-expiry batches) → picker scans and submits it with the bag / box label
→ order Packed → Pick List → Create → Delivery Note → Delivery Trip.
Orders filled from the DC must be picked before their Delivery Note; at a store the Pick List is optional.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

PICKER_ROLE = "Picker Packer"
PICKER_PERMISSIONS = {
	# doctype: rights beyond read
	"Pick List": ("write", "create", "submit", "print"),
	"Sales Order": (),
}


def online_orders_on(pick_list):
	orders = {row.sales_order for row in pick_list.locations if row.sales_order}
	return [so for so in orders if frappe.db.get_value("Sales Order", so, "nir_is_online_order")]


def store_warehouses():
	return set(frappe.get_all("Pharmacy Store", filters={"disabled": 0}, pluck="warehouse"))


def is_dc_location(warehouse):
	return bool(warehouse) and warehouse not in store_warehouses()


def require_package_label(doc, method=None):
	"""Pick List before_submit: an online-order pick is packed into a labelled bag / box."""
	if not online_orders_on(doc):
		return
	if not (doc.nir_package_label or "").strip():
		frappe.throw(_("Scan or enter the Bag / Box Label before submitting the pick"), title=_("Packing label required"))
	doc.nir_packed_by = frappe.session.user
	doc.nir_packed_on = now_datetime()


def update_orders(doc, method=None):
	"""Pick List saved / submitted / cancelled: Picking or Packed on the online order."""
	from pharmacy.online.delivery import refresh_status

	for so in online_orders_on(doc):
		refresh_status(so)


def require_pick_for_dc(doc, method=None):
	"""Delivery Note validate: online-order lines shipped from the DC must come through a submitted Pick List."""
	if doc.is_return:
		return
	missing = []
	for row in doc.items:
		if not row.against_sales_order or not is_dc_location(row.warehouse):
			continue
		if not frappe.db.get_value("Sales Order", row.against_sales_order, "nir_is_online_order"):
			continue
		if not row.against_pick_list or frappe.db.get_value("Pick List", row.against_pick_list, "docstatus") != 1:
			missing.append(f"#{row.idx} {row.item_code}")
	if missing:
		frappe.throw(_("Online order lines from the warehouse must be picked and packed first: {0}. "
			"Create a Pick List from the Sales Order, submit it, then make the Delivery Note from the Pick List.").format(", ".join(missing)),
			title=_("Pick and pack first"))


def pick_state(sales_order):
	"""'Packed' if a submitted Pick List covers the order, 'Picking' if only a draft exists, else None."""
	states = frappe.db.sql(
		"""select distinct pl.docstatus from `tabPick List Item` item join `tabPick List` pl on pl.name = item.parent
		where item.sales_order = %s and pl.docstatus < 2""",
		sales_order,
	)
	states = {d for (d,) in states}
	if 1 in states:
		return "Packed"
	if 0 in states:
		return "Picking"
	return None


def setup_picker_permissions():
	"""Role permissions for Picker Packer on Pick List (Custom DocPerm), idempotent."""
	from frappe.permissions import add_permission, update_permission_property

	if not frappe.db.exists("Role", PICKER_ROLE):
		return
	for doctype, rights in PICKER_PERMISSIONS.items():
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": PICKER_ROLE, "permlevel": 0}):
			add_permission(doctype, PICKER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, PICKER_ROLE, 0, right, 1, validate=False)
