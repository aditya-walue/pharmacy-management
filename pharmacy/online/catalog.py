"""Website catalogue: search by brand or generic (salt), product pages, offers, substitutes and pincode serviceability.

Everything here is open to guests. Schedule X and NDPS items never appear.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime, nowdate

from pharmacy.online import NOT_SOLD_ONLINE, get_settings
from pharmacy.overrides.pos_billing import sellable_batches
from pharmacy.overrides.quarantine import get_non_sellable
from pharmacy.pharmacy.substitutes import find_substitutes

PICKUP_READY_HOURS = 2
OPENING_HOUR = 9


# ---- locations and stock


def get_locations(pincode=None, pickup_store=None):
	"""Where an order can be filled from, nearest first: stores serving the pincode, then the DC."""
	settings = get_settings()
	if pickup_store:
		store = frappe.db.get_value("Pharmacy Store", {"name": pickup_store, "disabled": 0, "online_orders": 1},
			["name", "warehouse", "address"], as_dict=True)
		if not store:
			frappe.throw(_("{0} does not take online orders").format(pickup_store))
		return [frappe._dict(store=store.name, warehouse=store.warehouse, hours=PICKUP_READY_HOURS, cod=1, distance=0,
			delivery_type="Store Pickup", address=store.address)]

	rows = frappe.db.sql(
		"""select store.name as store, store.warehouse, store.address, pin.distance_km as distance,
			pin.delivery_hours as hours, pin.cod_allowed as cod, pin.delivery_type
		from `tabPharmacy Store Pincode` pin join `tabPharmacy Store` store on store.name = pin.parent
		where pin.pincode = %s and pin.is_active = 1 and store.disabled = 0 and store.online_orders = 1
		order by pin.distance_km asc, pin.delivery_hours asc""",
		(pincode or "").strip(),
		as_dict=True,
	)
	if settings.dc_warehouse and (rows or settings.dc_ships_to_all_pincodes):
		rows.append(frappe._dict(store=None, warehouse=settings.dc_warehouse, address=None, distance=9999,
			hours=cint(settings.dc_delivery_hours) or 48, cod=1, delivery_type="Standard"))
	return rows


def sellable_warehouses(warehouse):
	"""A store is one warehouse; the DC is every sellable bin under it."""
	if not frappe.db.get_value("Warehouse", warehouse, "is_group"):
		return [warehouse]
	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	leaves = frappe.get_all("Warehouse", filters={"lft": (">", lft), "rgt": ("<", rgt), "is_group": 0, "disabled": 0},
		fields=["name", "nir_warehouse_role"], order_by="lft")
	leaves = [w.name for w in leaves if w.nir_warehouse_role != "Transit"]
	blocked = set(get_non_sellable(leaves))
	return [w for w in leaves if w not in blocked]


def available_qty(item_code, warehouse, on_date=None):
	"""Sellable stock (unexpired, not held or quarantined) less what open orders have reserved, per bin."""
	result = {}
	for leaf in sellable_warehouses(warehouse):
		qty = sum(flt(b.qty) for b in sellable_batches(item_code, leaf, on_date or nowdate()))
		if not frappe.get_cached_value("Item", item_code, "has_batch_no"):
			qty = flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": leaf}, "actual_qty"))
		qty -= flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": leaf}, "reserved_qty"))
		if qty > 0:
			result[leaf] = qty
	return result


def expected_by(hours):
	"""Delivery time counted from now, or from opening next morning after the cut-off."""
	settings = get_settings()
	start = now_datetime()
	cutoff = settings.store_order_cutoff
	if cutoff and start.time() > get_datetime(f"{nowdate()} {cutoff}").time():
		start = get_datetime(f"{add_to_date(nowdate(), days=1)} {OPENING_HOUR:02d}:00:00")
	return add_to_date(start, hours=cint(hours))


# ---- pricing


def price_items(item_codes, customer=None, coupon_code=None):
	"""MRP (price list) and offer price for one pack, with the Pricing Rules that apply."""
	from erpnext.stock.get_item_details import get_item_details

	settings = get_settings()
	customer_group, territory = settings.customer_group, settings.territory
	if customer:
		customer_group, territory = frappe.db.get_value("Customer", customer, ["customer_group", "territory"])
	prices = {}
	for code in item_codes:
		uom = frappe.get_cached_value("Item", code, "sales_uom") or frappe.get_cached_value("Item", code, "stock_uom")
		details = get_item_details(frappe._dict(
			item_code=code, company=settings.company, doctype="Sales Order", transaction_date=nowdate(), qty=1, uom=uom,
			customer=customer, customer_group=customer_group, territory=territory, selling_price_list=settings.price_list,
			price_list_currency="INR", currency="INR", conversion_rate=1, plc_conversion_rate=1, coupon_code=coupon_code,
		))
		mrp = flt(details.price_list_rate)
		offer = flt(details.rate) or mrp
		prices[code] = frappe._dict(uom=uom, mrp=mrp, price=offer,
			discount_pct=flt((mrp - offer) / mrp * 100, 1) if mrp else 0, offers=offer_titles(details))
	return prices


def offer_titles(details):
	names = frappe.parse_json(details.get("pricing_rules") or "[]") if isinstance(details.get("pricing_rules"), str) else []
	if not names:
		return []
	return frappe.get_all("Pricing Rule", filters={"name": ("in", names)}, pluck="title")


# ---- website API


def item_card(code, price, stock=None):
	item = frappe.get_cached_value("Item", code, ["item_name", "brand", "nir_salt", "nir_strength", "nir_dosage_form",
		"nir_manufacturer", "nir_rx_required", "image"], as_dict=True)
	card = {
		"item_code": code, "item_name": item.item_name, "brand": item.brand, "generic": item.nir_salt,
		"strength": item.nir_strength, "dosage_form": item.nir_dosage_form, "manufacturer": item.nir_manufacturer,
		"image": item.image, "rx_required": item.nir_rx_required, "pack": price.uom, "mrp": price.mrp, "price": price.price,
		"discount_pct": price.discount_pct, "offers": price.offers,
	}
	if stock is not None:
		card["in_stock"] = stock > 0
	return card


def stock_for_pincode(item_code, pincode):
	return sum(sum(available_qty(item_code, loc.warehouse).values()) for loc in get_locations(pincode))


def online_items(conditions="", values=None, limit=20):
	values = dict(values or {}, blocked=NOT_SOLD_ONLINE, limit=cint(limit) or 20)
	return frappe.db.sql_list(
		f"""select item.name from `tabItem` item
		left join `tabSalt` salt on salt.name = item.nir_salt
		where item.disabled = 0 and item.is_sales_item = 1 and item.has_variants = 0
			and ifnull(item.nir_regulatory_category, '') not in %(blocked)s {conditions}
		order by item.item_name limit %(limit)s""",
		values,
	)


@frappe.whitelist(allow_guest=True)
def search(query: str, pincode: str | None = None, limit: int = 20):
	"""Brand, name, code, barcode or generic (salt) name."""
	query = (query or "").strip()
	if len(query) < 2:
		return []
	barcode_item = frappe.db.get_value("Item Barcode", {"barcode": query}, "parent")
	if barcode_item:
		codes = online_items("and item.name = %(code)s", {"code": barcode_item})
	else:
		codes = online_items(
			"and (item.name like %(like)s or item.item_name like %(like)s or item.brand like %(like)s or salt.salt_name like %(like)s)",
			{"like": f"%{query}%"}, limit)
	prices = price_items(codes)
	# no MRP on the price list, nothing to sell
	return [item_card(c, prices[c], stock_for_pincode(c, pincode) if pincode else None) for c in codes if prices[c].mrp > 0]


@frappe.whitelist(allow_guest=True)
def get_product(item_code: str, pincode: str | None = None):
	"""Product page: details, MRP, offer price, offers and substitutes (cheapest first)."""
	if not online_items("and item.name = %(code)s", {"code": item_code}):
		frappe.throw(_("Product not available online"), frappe.DoesNotExistError)
	subs = [s.item_code for s in find_substitutes(item_code) if online_items("and item.name = %(code)s", {"code": s.item_code})]
	prices = price_items([item_code, *subs])
	item = frappe.get_cached_value("Item", item_code, ["description", "nir_marketer", "nir_storage_condition"], as_dict=True)
	product = item_card(item_code, prices[item_code], stock_for_pincode(item_code, pincode) if pincode else None)
	product.update({
		"description": item.description, "marketer": item.nir_marketer, "storage": item.nir_storage_condition,
		"substitutes": sorted((item_card(s, prices[s]) for s in subs if prices[s].mrp > 0), key=lambda s: s["price"]),
	})
	if pincode:
		product["delivery"] = check_pincode(pincode)
	return product


@frappe.whitelist(allow_guest=True)
def check_pincode(pincode: str):
	"""Serviceability, delivery time, COD and pickup stores for a pincode."""
	pincode = (pincode or "").strip()
	settings = get_settings()
	locations = get_locations(pincode)
	stores = [loc for loc in locations if loc.store]
	if not locations:
		return {"pincode": pincode, "serviceable": False, "message": _("We do not deliver to {0} yet").format(pincode)}
	fastest = min(locations, key=lambda loc: cint(loc.hours))
	return {
		"pincode": pincode,
		"serviceable": True,
		"home_delivery": True,
		"delivery_type": fastest.delivery_type,
		"expected_by": expected_by(fastest.hours),
		"cod_available": bool(settings.cod_enabled and any(cint(loc.cod) for loc in locations)),
		"cod_limit": flt(settings.cod_max_amount),
		"delivery_charge": flt(settings.delivery_charge),
		"free_delivery_above": flt(settings.free_delivery_above),
		"pickup_stores": [{"store": s.store, "address": address_text(s.address), "distance_km": s.distance,
			"ready_by": expected_by(PICKUP_READY_HOURS)} for s in stores],
	}


def address_text(address):
	if not address:
		return None
	a = frappe.db.get_value("Address", address, ["address_line1", "address_line2", "city", "pincode"], as_dict=True) or {}
	return ", ".join(v for v in (a.get("address_line1"), a.get("address_line2"), a.get("city"), a.get("pincode")) if v)
