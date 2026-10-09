"""Block transactions when a party's licence doesn't cover the items' regulatory category (MD-10)."""

import frappe
from frappe import _
from frappe.utils import getdate

RETAIL = {"20", "21"}
WHOLESALE = {"20B", "21B"}
FSSAI = {"FSSAI"}

# licence forms that permit dealing in each category; Cosmetic needs no licence
FORMS_FOR_CATEGORY = {
	"retail": {
		"OTC": RETAIL,
		"Schedule H": RETAIL,
		"Schedule H1": RETAIL,
		"NDPS": RETAIL,
		"Schedule X": {"20F"},
		"FSSAI": FSSAI,
	},
	"wholesale": {
		"OTC": WHOLESALE,
		"Schedule H": WHOLESALE,
		"Schedule H1": WHOLESALE,
		"NDPS": WHOLESALE,
		"Schedule X": {"20G"},
		"FSSAI": FSSAI,
	},
}
FORMS_FOR_CATEGORY["any"] = {
	category: FORMS_FOR_CATEGORY["retail"][category] | FORMS_FOR_CATEGORY["wholesale"][category]
	for category in FORMS_FOR_CATEGORY["retail"]
}


def validate_party_licence(doc, method=None):
	if doc.get("is_return") or doc.get("is_consolidated"):
		# returns move goods back to where they came from; consolidated invoices were checked as POS Invoices
		return

	if doc.doctype == "Stock Entry" and doc.purpose != "Material Transfer":
		return

	date = getdate(doc.get("posting_date") or doc.get("transaction_date"))
	for party_type, party, scope, items in get_checks(doc):
		categories = get_categories(items)
		if categories:
			check_licence(party_type, party, scope, categories, date)


def get_checks(doc):
	"""(party type, party, retail/wholesale/any, item rows) for every party whose licence must cover the goods."""
	items = doc.get("items") or []

	if doc.doctype in ("Purchase Order", "Purchase Receipt", "Purchase Invoice"):
		yield "Supplier", doc.supplier, "wholesale", items
		for warehouse, rows in group_by_warehouse(items, "warehouse", doc.get("set_warehouse")):
			yield "Warehouse", warehouse, "any", rows

	elif doc.doctype in ("Sales Invoice", "POS Invoice", "Delivery Note"):
		licensed_customer = has_licences("Customer", doc.customer)
		if licensed_customer:
			yield "Customer", doc.customer, "any", items

		# selling to a licensed business is wholesale; to a consumer, retail
		scope = "wholesale" if licensed_customer else "retail"
		for warehouse, rows in group_by_warehouse(items, "warehouse", doc.get("set_warehouse")):
			yield "Warehouse", warehouse, scope, rows

	elif doc.doctype == "Stock Entry":
		for row in items:
			# moves within one licensed site (DC to its own bins) need no check
			if row.t_warehouse and get_licence_holder(row.t_warehouse) != get_licence_holder(row.s_warehouse):
				yield "Warehouse", row.t_warehouse, "any", [row]


def group_by_warehouse(items, fieldname, default=None):
	groups = {}
	for row in items:
		warehouse = row.get(fieldname) or default
		if warehouse:
			groups.setdefault(warehouse, []).append(row)
	return groups.items()


def get_categories(items):
	item_codes = list({row.item_code for row in items if row.item_code})
	if not item_codes:
		return {}

	categories = frappe.get_all(
		"Item",
		filters={"name": ("in", item_codes), "nir_regulatory_category": ("in", list(FORMS_FOR_CATEGORY["any"]))},
		fields=["name", "nir_regulatory_category"],
	)
	return {item.name: item.nir_regulatory_category for item in categories}


def check_licence(party_type, party, scope, categories, date):
	if party_type == "Warehouse":
		holder = get_licence_holder(party)
		if not holder:
			frappe.throw(
				_("Warehouse {0} has no Drug Licence on it or on a parent warehouse").format(party),
				title=_("Licence missing"),
			)
		party = holder

	held = get_valid_forms(party_type, party, date)
	for item_code, category in categories.items():
		allowed = FORMS_FOR_CATEGORY[scope][category]
		if not held & allowed:
			frappe.throw(
				_("{0} {1} has no valid licence on {2} for {3} item {4}. Needs Form {5}.").format(
					party_type,
					party,
					frappe.format(date, "Date"),
					category,
					item_code,
					" / ".join(sorted(allowed)),
				),
				title=_("Licence not valid"),
			)


def get_valid_forms(party_type, party, date):
	return set(
		frappe.get_all(
			"Drug Licence",
			filters={
				"party_type": party_type,
				"party": party,
				"valid_from": ("<=", date),
				"valid_upto": (">=", date),
			},
			pluck="licence_form",
		)
	)


def has_licences(party_type, party):
	return bool(party) and frappe.db.exists("Drug Licence", {"party_type": party_type, "party": party})


def get_licence_holder(warehouse):
	"""Nearest warehouse up the tree (itself included) that holds a licence; bins and zones use their DC's."""
	if not warehouse:
		return None

	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	ancestors = frappe.get_all(
		"Warehouse",
		filters={"lft": ("<=", lft), "rgt": (">=", rgt)},
		order_by="lft desc",
		pluck="name",
	)
	licensed = set(
		frappe.get_all(
			"Drug Licence",
			filters={"party_type": "Warehouse", "party": ("in", ancestors)},
			pluck="party",
		)
	)
	return next((name for name in ancestors if name in licensed), None)
