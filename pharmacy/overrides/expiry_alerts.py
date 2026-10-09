"""Near-expiry alerts at 180, 90, 60 and 30 days (WH-06)."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.inventory import enrich, get_batch_stock
from pharmacy.overrides.warehouse_layout import get_layout

ALERT_DAYS = (180, 90, 60, 30)
DC_ROLES = ("Warehouse Manager", "Category Manager")
STORE_ROLES = ("Store Pharmacist",)
REPORT = "Near Expiry Stock"


def send_near_expiry_alerts():
	"""Daily: one notification per threshold reached today, to DC roles and, for store stock, store pharmacists."""
	rows = [r for r in enrich(get_batch_stock()) if flt(r.qty) > 0 and r.days_to_expiry in ALERT_DAYS]
	if not rows:
		return

	layout = get_layout()
	for days in ALERT_DAYS:
		batch_rows = [r for r in rows if r.days_to_expiry == days]
		if not batch_rows:
			continue
		for roles, in_scope in (
			(DC_ROLES, lambda r: not is_store_stock(r.warehouse, layout)),
			(STORE_ROLES, lambda r: is_store_stock(r.warehouse, layout)),
		):
			scoped = [r for r in batch_rows if in_scope(r)]
			if scoped:
				notify(roles, days, scoped)


def is_store_stock(warehouse, layout):
	w = layout.get(warehouse)
	while w:
		if w.nir_warehouse_role == "Store":
			return True
		parent = frappe.db.get_value("Warehouse", w.name, "parent_warehouse")
		w = layout.get(parent)
	return False


def notify(roles, days, rows):
	value = sum(flt(r.value) for r in rows)
	subject = _("{0} batches ({1}) reach {2} days to expiry today").format(
		len({(r.item_code, r.batch_no) for r in rows}), fmt_money(value), days
	)
	users = {u for role in roles for u in get_users_with_role(role)}
	for user in users:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Report",
				"document_name": REPORT,
				"subject": subject,
			}
		).insert(ignore_permissions=True)
