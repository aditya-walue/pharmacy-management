"""Store billing rules (POS-01 to POS-04), enforced on POS Invoice and POS Sales Invoice whatever the screen.

- Earliest-expiry sellable batch by default; expired, held or recalled batches can't be billed.
- Loose sale of strips / tablets for loose-sale items, priced from the batch's pack MRP.
- Price list = batch MRP for the unit sold, so the selling price can never exceed MRP.
- Pricing Rule discounts apply automatically; manual discount above the user's role limit needs approval.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.inventory import enrich, get_batch_stock
from pharmacy.overrides.quarantine import get_non_sellable
from pharmacy.overrides.stock_hold import find_hold, get_active_holds
from pharmacy.pharmacy.substitutes import get_substitutes

UNLIMITED_ROLES = ("System Manager", "Administrator")


def is_store_bill(doc):
	return doc.doctype == "POS Invoice" or (doc.doctype == "Sales Invoice" and (doc.get("is_pos") or doc.get("is_created_using_pos")))


def apply_pos_rules(doc, method=None):
	if not is_store_bill(doc) or doc.get("is_return"):
		return

	inclusive = any(t.get("included_in_print_rate") for t in doc.get("taxes") or [])
	holds = get_active_holds({r.item_code for r in doc.items})
	for row in doc.items:
		item = frappe.get_cached_value(
			"Item", row.item_code, ["has_batch_no", "nir_loose_sale", "sales_uom", "stock_uom"], as_dict=True
		)
		if not item.has_batch_no:
			continue
		if not row.batch_no:
			row.batch_no = pick_batch(row, doc, holds)
			row.use_serial_batch_fields = 1
		batch = check_batch(row, doc, holds)
		if not row.get("is_free_item"):
			price_row(row, item, batch, inclusive)

	update_discount_approval(doc)
	doc.calculate_taxes_and_totals()


def sellable_batches(item_code, warehouse, on_date, holds=None):
	"""Batches with stock here, unexpired and not on hold, earliest expiry first."""
	if not warehouse or warehouse in get_non_sellable([warehouse]):
		return []
	holds = holds if holds is not None else get_active_holds([item_code])
	rows = [
		r for r in enrich(get_batch_stock(warehouses=[warehouse], item_codes=[item_code]))
		if r.batch_no and flt(r.qty) > 0
		and not (r.expiry_date and getdate(r.expiry_date) < getdate(on_date))
		and not find_hold(holds, item_code, [r.batch_no], warehouse)
	]
	return sorted(rows, key=lambda r: getdate(r.expiry_date) if r.expiry_date else getdate("9999-12-31"))


def pick_batch(row, doc, holds):
	stock_qty = flt(row.qty) * (flt(row.conversion_factor) or 1)
	batches = sellable_batches(row.item_code, row.warehouse, doc.posting_date, holds)
	batch = next((b for b in batches if flt(b.qty) >= stock_qty), batches[0] if batches else None)
	if not batch:
		frappe.throw(_("Row #{0}: no sellable batch of {1} in {2}").format(row.idx, row.item_code, row.warehouse))
	return batch.batch_no


def check_batch(row, doc, holds):
	batch = frappe.db.get_value("Batch", row.batch_no, ["name", "item", "expiry_date", "nir_mrp", "nir_mrp_uom", "disabled"], as_dict=True)
	if not batch or batch.item != row.item_code:
		frappe.throw(_("Row #{0}: batch {1} is not of {2}").format(row.idx, row.batch_no, row.item_code))
	if batch.disabled:
		frappe.throw(_("Row #{0}: batch {1} is disabled").format(row.idx, row.batch_no))
	if batch.expiry_date and getdate(batch.expiry_date) < getdate(doc.posting_date):
		frappe.throw(_("Row #{0}: batch {1} of {2} expired on {3} and cannot be billed").format(
			row.idx, row.batch_no, row.item_code, frappe.format(batch.expiry_date, "Date")), title=_("Expired batch"))
	hold = find_hold(holds, row.item_code, [row.batch_no], row.warehouse)
	if hold:
		frappe.throw(_("Row #{0}: batch {1} is on {2} hold ({3}) and cannot be billed").format(
			row.idx, row.batch_no, hold.hold_type.lower(), hold.name), title=_("Batch on hold"))
	if not flt(batch.nir_mrp):
		frappe.throw(_("Row #{0}: batch {1} has no MRP").format(row.idx, row.batch_no))
	return batch


def price_row(row, item, batch, inclusive):
	"""Price list = batch MRP for the unit sold; loose units only for loose-sale items."""
	pack_uom = batch.nir_mrp_uom or item.sales_uom or item.stock_uom
	pack_factor = uom_factor(row.item_code, pack_uom, item.stock_uom)
	row_factor = flt(row.conversion_factor) or uom_factor(row.item_code, row.uom, item.stock_uom)
	if row.uom != pack_uom and not item.nir_loose_sale:
		frappe.throw(_("Row #{0}: {1} is sold only per {2}").format(row.idx, row.item_code, pack_uom), title=_("No loose sale"))
	if row_factor > pack_factor:
		frappe.throw(_("Row #{0}: sell {1} per {2} or smaller").format(row.idx, row.item_code, pack_uom))

	unit_mrp = flt(batch.nir_mrp) / pack_factor * row_factor
	gst = gst_rate(row)
	list_price = unit_mrp if inclusive else unit_mrp / (1 + gst / 100)

	discount = flt(row.discount_percentage)
	if not discount and flt(row.discount_amount) and flt(row.price_list_rate):
		discount = flt(row.discount_amount) / flt(row.price_list_rate) * 100
	row.nir_unit_mrp = unit_mrp
	row.nir_auto_discount = auto_discount(row)
	row.price_list_rate = list_price
	row.discount_percentage = discount
	row.rate = flt(list_price * (1 - discount / 100), row.precision("rate"))
	row.discount_amount = list_price - row.rate

	selling = row.rate if inclusive else row.rate * (1 + gst / 100)
	if selling > unit_mrp + 0.01:
		frappe.throw(_("Row #{0}: price {1} is above the batch MRP {2}").format(
			row.idx, frappe.format(selling, "Currency"), frappe.format(unit_mrp, "Currency")), title=_("Above MRP"))


def uom_factor(item_code, uom, stock_uom):
	if not uom or uom == stock_uom:
		return 1
	return flt(frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor")) or 1


def gst_rate(row):
	if row.get("item_tax_template"):
		return flt(frappe.db.get_value("Item Tax Template", row.item_tax_template, "gst_rate"))
	return 0


def auto_discount(row):
	"""Discount % from the Pricing Rules ERPNext applied to the line."""
	rules = row.get("pricing_rules")
	if not rules:
		return 0
	try:
		names = json.loads(rules)
	except ValueError:
		names = [r.strip() for r in rules.split(",") if r.strip()]
	values = frappe.get_all(
		"Pricing Rule", filters={"name": ("in", names), "rate_or_discount": "Discount Percentage"}, pluck="discount_percentage"
	)
	return max([flt(v) for v in values] or [0])


def get_user_limit(user=None):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	if user == "Administrator" or set(UNLIMITED_ROLES) & set(roles):
		return 100
	limits = frappe.get_all("POS Discount Limit", filters={"role": ("in", roles)}, pluck="max_discount_pct")
	return max([flt(v) for v in limits] or [0])


def manual_discounts(doc):
	return {row.name or row.idx: max(flt(row.discount_percentage) - flt(row.nir_auto_discount), 0) for row in doc.items}


def signature(doc):
	lines = sorted((r.item_code, r.batch_no or "", r.uom or "", flt(r.qty), round(flt(r.discount_percentage), 2)) for r in doc.items)
	return hashlib.sha1(json.dumps(lines).encode()).hexdigest()


def update_discount_approval(doc):
	requested = max(manual_discounts(doc).values() or [0])
	doc.nir_discount_requested = requested
	if requested <= get_user_limit(doc.owner if not doc.is_new() else frappe.session.user) + 0.0001:
		doc.nir_discount_approval = "Not Needed"
	elif doc.nir_discount_signature and doc.nir_discount_signature == signature(doc):
		doc.nir_discount_approval = "Approved"
	else:
		doc.nir_discount_approval = "Pending"
		doc.nir_discount_approved_by = doc.nir_discount_approved_on = doc.nir_discount_signature = None
		doc.flags.nir_notify_discount = True


def require_discount_approval(doc, method=None):
	if is_store_bill(doc) and doc.get("nir_discount_approval") == "Pending":
		frappe.throw(_("A {0}% discount is above your limit and needs approval before billing").format(
			flt(doc.nir_discount_requested, 2)), title=_("Discount approval pending"))


def notify_discount_approvers(doc, method=None):
	if not doc.flags.nir_notify_discount:
		return
	doc.flags.nir_notify_discount = False
	roles = frappe.get_all("POS Discount Limit",
		filters={"can_approve_overrides": 1, "max_discount_pct": (">=", flt(doc.nir_discount_requested))}, pluck="role")
	users = {u for role in roles for u in get_users_with_role(role)} - {doc.owner}
	for user in users:
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": doc.doctype,
			"document_name": doc.name, "subject": _("Approve {0}% discount on {1} ({2})").format(
				flt(doc.nir_discount_requested, 2), doc.name, doc.customer_name or doc.customer)}).insert(ignore_permissions=True)


@frappe.whitelist()
def approve_discount(doctype: str, name: str):
	if doctype not in ("POS Invoice", "Sales Invoice"):
		frappe.throw(_("Not a store bill"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.docstatus != 0 or doc.nir_discount_approval != "Pending":
		frappe.throw(_("No discount is waiting for approval on {0}").format(name))
	if frappe.session.user == doc.owner:
		frappe.throw(_("You created this bill, so someone else must approve its discount."))
	if approval_limit() < flt(doc.nir_discount_requested):
		frappe.throw(_("Your approval limit is below {0}%").format(flt(doc.nir_discount_requested, 2)), frappe.PermissionError)

	doc.nir_discount_signature = signature(doc)
	doc.nir_discount_approved_by = frappe.session.user
	doc.nir_discount_approved_on = now_datetime()
	doc.flags.ignore_permissions = True
	doc.save()
	doc.add_comment("Comment", _("Discount of {0}% approved").format(flt(doc.nir_discount_requested, 2)))


def approval_limit():
	"""Highest discount this user may approve for others."""
	if set(UNLIMITED_ROLES) & set(frappe.get_roles()) or frappe.session.user == "Administrator":
		return 100
	limits = frappe.get_all("POS Discount Limit",
		filters={"role": ("in", frappe.get_roles()), "can_approve_overrides": 1}, pluck="max_discount_pct")
	return max([flt(v) for v in limits] or [0])


@frappe.whitelist()
def pharmacy_search(text: str, warehouse: str, posting_date: str | None = None):
	"""POS-01: find by barcode, brand / name / code or salt; stock, sellable batches (expiry, MRP) and substitutes."""
	frappe.has_permission("Item", "read", throw=True)
	text = (text or "").strip()
	if len(text) < 2:
		return []

	by_barcode = frappe.db.get_value("Item Barcode", {"barcode": text}, "parent")
	if by_barcode:
		codes = [by_barcode]
	else:
		like = f"%{text}%"
		codes = frappe.db.sql_list(
			"""select item.name from `tabItem` item
			left join `tabSalt` salt on salt.name = item.nir_salt
			where item.disabled = 0 and item.is_sales_item = 1
				and (item.name like %(like)s or item.item_name like %(like)s or item.brand like %(like)s or salt.salt_name like %(like)s)
			order by item.item_name limit 20""",
			{"like": like},
		)

	results = []
	for code in codes:
		item = frappe.db.get_value("Item", code, ["item_name", "nir_salt", "nir_strength", "nir_loose_sale", "sales_uom",
			"stock_uom", "nir_regulatory_category", "nir_rx_required"], as_dict=True)
		batches = sellable_batches(code, warehouse, posting_date or frappe.utils.today())
		uoms = frappe.get_all("UOM Conversion Detail", filters={"parent": code}, fields=["uom", "conversion_factor"], order_by="conversion_factor")
		results.append({
			"item_code": code, "item_name": item.item_name, "salt": item.nir_salt, "strength": item.nir_strength,
			"category": item.nir_regulatory_category, "rx": item.nir_rx_required, "loose": item.nir_loose_sale,
			"stock_uom": item.stock_uom, "sales_uom": item.sales_uom, "uoms": uoms,
			"stock": sum(flt(b.qty) for b in batches),
			"batches": [{"batch_no": b.batch_no, "expiry_date": b.expiry_date, "days_to_expiry": b.days_to_expiry,
				"mrp": b.mrp, "mrp_uom": b.mrp_uom, "qty": b.qty} for b in batches],
			"substitutes": [s.item_code for s in get_substitutes(code)][:5] if item.nir_salt else [],
		})
	return results
