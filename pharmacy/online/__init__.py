"""Online orders (Flow 3): website API for Frappe Builder pages, pharmacist check, allocation and billing."""

import frappe
from frappe import _

NOT_SOLD_ONLINE = ("Schedule X", "NDPS")


def get_settings():
	settings = frappe.get_cached_doc("Online Order Settings")
	if not settings.company:
		frappe.throw(_("Online ordering is not set up yet (Online Order Settings)"))
	return settings


def check_sold_online(item_code):
	category = frappe.get_cached_value("Item", item_code, "nir_regulatory_category")
	if category in NOT_SOLD_ONLINE:
		frappe.throw(_("{0} is a {1} drug and is sold only at the store against a prescription").format(
			frappe.get_cached_value("Item", item_code, "item_name"), category), title=_("Not sold online"))
