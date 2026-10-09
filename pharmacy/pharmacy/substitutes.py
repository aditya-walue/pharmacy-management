import frappe
from frappe.utils.nestedset import get_descendants_of

PRIVATE_LABEL_GROUP = "Private Label"


@frappe.whitelist()
def get_substitutes(item_code: str, warehouse: str = None) -> list[dict]:
	"""Enabled items with the same salt and strength, private-label equivalents first."""
	frappe.has_permission("Item", "read", throw=True)
	return find_substitutes(item_code, warehouse)


def find_substitutes(item_code, warehouse=None):
	salt, strength = frappe.db.get_value("Item", item_code, ["nir_salt", "nir_strength"]) or (None, None)
	if not salt or not strength:
		return []

	substitutes = frappe.get_all(
		"Item",
		filters={
			"nir_salt": salt,
			"nir_strength": strength,
			"disabled": 0,
			"name": ("!=", item_code),
		},
		fields=["name as item_code", "item_name", "brand", "item_group", "nir_dosage_form", "standard_rate"],
		order_by="item_name asc",
	)

	private_label_groups = set(get_private_label_groups())
	for item in substitutes:
		item.is_private_label = int(item.item_group in private_label_groups)
		if warehouse:
			item.actual_qty = frappe.db.get_value(
				"Bin", {"item_code": item.item_code, "warehouse": warehouse}, "actual_qty"
			) or 0.0

	# stable sort keeps item_name order within each group
	return sorted(substitutes, key=lambda item: not item.is_private_label)


def get_private_label_groups():
	if not frappe.db.exists("Item Group", PRIVATE_LABEL_GROUP):
		return []

	return [PRIVATE_LABEL_GROUP, *get_descendants_of("Item Group", PRIVATE_LABEL_GROUP)]
