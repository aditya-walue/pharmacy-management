"""Purchase terms on ERPNext natives.

- Rate contract: a Purchasing Blanket Order; each line carries PTR and trade discount, and its rate is
  PTR less trade discount, valid between the order's From and To dates.
- Schemes such as 10+1 free: Pricing Rules (buying, product discount, same item, recursive). ERPNext adds
  the free row at rate 0 on validate.
- Cash discount: the supplier's Payment Terms Template with an early-payment discount.
Trade discount belongs on the contract only; a price-discount Pricing Rule on top would apply it twice.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

# a rate typed this far above the contract counts as a variance (avoids rounding noise)
RATE_TOLERANCE = 0.005


def validate_blanket_order(doc, method=None):
	if doc.blanket_order_type != "Purchasing":
		return

	for row in doc.items:
		if flt(row.nir_ptr):
			# a line without its own trade discount takes the contract's default
			row.nir_trade_discount_pct = flt(row.nir_trade_discount_pct) or flt(doc.nir_trade_discount_pct)
			row.rate = flt(row.nir_ptr) * (1 - row.nir_trade_discount_pct / 100)

	validate_overlap(doc)


def validate_overlap(doc):
	"""Only one rate contract per supplier and item may be in force on any date."""
	item_codes = [row.item_code for row in doc.items]
	if len(item_codes) != len(set(item_codes)):
		frappe.throw(_("An item can be listed only once in a rate contract"))

	bo = frappe.qb.DocType("Blanket Order")
	bo_item = frappe.qb.DocType("Blanket Order Item")
	overlap = (
		frappe.qb.from_(bo)
		.join(bo_item)
		.on(bo_item.parent == bo.name)
		.select(bo.name, bo_item.item_code)
		.where(
			(bo.blanket_order_type == "Purchasing")
			& (bo.supplier == doc.supplier)
			& (bo.company == doc.company)
			& (bo.docstatus == 1)
			& (bo.name != doc.name)
			& (bo_item.item_code.isin(item_codes))
			& (bo.from_date <= doc.to_date)
			& (bo.to_date >= doc.from_date)
		)
		.limit(1)
		.run(as_dict=True)
	)
	if overlap:
		frappe.throw(
			_("Item {0} already has a rate contract with {1} for these dates in {2}").format(
				overlap[0].item_code, doc.supplier, overlap[0].name
			),
			title=_("Overlapping rate contract"),
		)


def apply_rate_contracts(doc, method=None):
	"""Price PO lines from the supplier's rate contract and flag lines priced above it.

	A contract's price is applied when it first attaches to a line (or the contract rate changes);
	after that a buyer may edit the rate, and a higher rate is flagged for approval.
	"""
	contracts = get_contract_lines(doc)
	repriced = False

	for row in doc.items:
		if row.get("is_free_item"):
			continue

		contract = contracts.get(row.item_code)
		if not contract:
			row.nir_rate_contract = row.nir_contract_rate = None
			row.nir_contract_variance = 0
			continue

		if row.nir_rate_contract != contract.name or flt(row.nir_contract_rate) != flt(contract.rate):
			row.nir_rate_contract = contract.name
			row.nir_contract_rate = contract.rate
			if flt(contract.nir_ptr):
				row.price_list_rate = contract.nir_ptr
				row.discount_percentage = flt(contract.nir_trade_discount_pct)
			row.rate = contract.rate
			repriced = True

		row.nir_contract_variance = int(flt(row.rate) > flt(contract.rate) + RATE_TOLERANCE)

	if repriced:
		doc.calculate_taxes_and_totals()


def get_contract_lines(doc):
	item_codes = list({row.item_code for row in doc.items if row.item_code and not row.get("is_free_item")})
	if not item_codes or not doc.supplier:
		return {}

	date = getdate(doc.transaction_date)
	bo = frappe.qb.DocType("Blanket Order")
	bo_item = frappe.qb.DocType("Blanket Order Item")
	lines = (
		frappe.qb.from_(bo)
		.join(bo_item)
		.on(bo_item.parent == bo.name)
		.select(bo.name, bo_item.item_code, bo_item.rate, bo_item.nir_ptr, bo_item.nir_trade_discount_pct)
		.where(
			(bo.blanket_order_type == "Purchasing")
			& (bo.supplier == doc.supplier)
			& (bo.company == doc.company)
			& (bo.docstatus == 1)
			& (bo.from_date <= date)
			& (bo.to_date >= date)
			& (bo_item.item_code.isin(item_codes))
		)
		.run(as_dict=True)
	)
	return {line.item_code: line for line in lines}


def get_variance_items(doc):
	return [row.item_code for row in doc.items if row.get("nir_contract_variance")]
