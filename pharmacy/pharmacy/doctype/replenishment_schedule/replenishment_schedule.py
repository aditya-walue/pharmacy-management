# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ReplenishmentSchedule(Document):
	def validate(self):
		self.validate_scope_and_target()

	def validate_scope_and_target(self):
		if self.scope == "Cluster" and not self.cluster:
			frappe.throw(_("Cluster is required when Scope is 'Cluster'."), frappe.ValidationError)
		if self.scope == "Store" and not self.store:
			frappe.throw(_("Store is required when Scope is 'Store'."), frappe.ValidationError)

		if self.applies_to == "Item" and not self.item:
			frappe.throw(_("Item is required when Applies To is 'Item'."), frappe.ValidationError)
		if self.applies_to == "Item Group" and not self.item_group:
			frappe.throw(_("Item Group is required when Applies To is 'Item Group'."), frappe.ValidationError)
		if self.applies_to == "ABC Class" and not self.abc_class:
			frappe.throw(_("ABC Class is required when Applies To is 'ABC Class'."), frappe.ValidationError)


def get_effective_replenishment_schedule(item_code: str, store: str = None, cluster: str = None) -> dict:
	"""Return effective replenishment schedule (frequency, order_days, reorder_level, reorder_qty).

	Resolution Hierarchy:
	1. Store Override (Item -> Item Group -> ABC Class -> Global)
	2. Cluster Override (Item -> Item Group -> ABC Class -> Global)
	3. All Stores Default (Item -> Item Group -> ABC Class -> Global)
	"""
	if not item_code:
		return get_default_schedule_dict()

	item = frappe.db.get_value("Item", item_code, ["item_group", "nir_abc_class"], as_dict=True)
	item_group = item.get("item_group") if item else None
	abc_class = item.get("nir_abc_class") if item else "B"

	if store and not cluster:
		cluster = frappe.db.get_value("Pharmacy Store", store, "cluster")

	# Build scope levels to search in priority order
	scope_levels = []
	if store:
		scope_levels.append(("Store", store))
	if cluster:
		scope_levels.append(("Cluster", cluster))
	scope_levels.append(("All Stores", None))

	# Build applies_to targets in priority order
	target_levels = [
		("Item", item_code),
		("Item Group", item_group),
		("ABC Class", abc_class),
		("Global", None),
	]

	for scope_type, scope_val in scope_levels:
		for target_type, target_val in target_levels:
			if target_type == "Item Group" and not target_val:
				continue
			if target_type == "ABC Class" and not target_val:
				continue

			filters = {
				"scope": scope_type,
				"applies_to": target_type,
				"disabled": 0,
				"nir_approval_status": "Approved",
			}
			if scope_type == "Cluster":
				filters["cluster"] = scope_val
			elif scope_type == "Store":
				filters["store"] = scope_val

			if target_type == "Item":
				filters["item"] = target_val
			elif target_type == "Item Group":
				filters["item_group"] = target_val
			elif target_type == "ABC Class":
				filters["abc_class"] = target_val

			schedule = frappe.get_all(
				"Replenishment Schedule",
				filters=filters,
				fields=["name", "frequency", "order_days", "reorder_level", "reorder_qty", "scope", "applies_to"],
				limit=1,
			)

			if schedule:
				res = schedule[0]
				return {
					"schedule_name": res.name,
					"frequency": res.frequency,
					"order_days": res.order_days or "Daily",
					"reorder_level": res.reorder_level,
					"reorder_qty": res.reorder_qty,
					"scope": res.scope,
					"applies_to": res.applies_to,
				}

	return get_default_schedule_dict()


def get_default_schedule_dict():
	return {
		"schedule_name": None,
		"frequency": "Daily",
		"order_days": "Daily",
		"reorder_level": 10.0,
		"reorder_qty": 50.0,
		"scope": "All Stores",
		"applies_to": "Global",
	}
