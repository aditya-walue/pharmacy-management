"""Website cart and checkout. The cart is a draft Sales Order; placing it makes it the customer's order.

Order life (Sales Order "Online Status"):
Cart -> Prescription Review (Rx items) -> Awaiting Payment (online) -> Confirmed -> Partly Dispatched / Dispatched -> Delivered
COD orders skip Awaiting Payment. A rejected prescription ends in Rejected; a customer can cancel until it is confirmed.
"""

import functools

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate

from pharmacy.online import check_sold_online, get_settings
from pharmacy.online.catalog import available_qty, expected_by, get_locations
from pharmacy.overrides.customer import normalise_mobile

CART = "Cart"
DELIVERY_CHARGE_DESCRIPTION = "Delivery Charge"


# ---- customer of the logged-in website user


def require_login():
	if website_user() == "Guest":
		frappe.throw(_("Log in to continue"), frappe.PermissionError)


def website_user():
	return frappe.local.flags.get("website_user") or frappe.session.user


def website_api(fn):
	"""Whitelisted for logged-in website users. The customer is always the caller's own; ERPNext's selling code then
	runs with full rights, because website users have no desk permissions on Sales Order, Address or Payment Request."""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if frappe.session.user == "Guest":
			frappe.throw(_("Log in to continue"), frappe.PermissionError)
		user = frappe.session.user
		frappe.local.flags.website_user = user
		frappe.set_user("Administrator")
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user(user)
			frappe.local.flags.website_user = None

	return frappe.whitelist()(wrapper)


def get_customer(create=True):
	require_login()
	customer = frappe.db.get_value("Portal User", {"user": website_user(), "parenttype": "Customer"}, "parent")
	if customer or not create:
		return customer
	settings = get_settings()
	user = frappe.get_cached_doc("User", website_user())
	mobile = normalise_mobile(user.mobile_no or user.phone)
	if mobile and frappe.db.exists("Customer", {"nir_mobile": mobile}):
		# a store customer with this number becomes the website customer too
		customer = frappe.get_doc("Customer", {"nir_mobile": mobile})
		customer.append("portal_users", {"user": user.name})
		customer.save(ignore_permissions=True)
		return customer.name
	customer = frappe.get_doc({
		"doctype": "Customer", "customer_name": user.full_name or user.name, "customer_type": "Individual",
		"customer_group": settings.customer_group, "territory": settings.territory, "nir_mobile": mobile or None,
		"portal_users": [{"user": user.name}],
	})
	customer.flags.ignore_permissions = True
	customer.insert()
	# website sign-ups need no back-office approval
	if customer.meta.has_field("nir_approval_status"):
		customer.db_set({"nir_approval_status": "Approved", "disabled": 0})
	return customer.name


@website_api
def set_profile(full_name: str | None = None, mobile: str | None = None):
	customer = frappe.get_doc("Customer", get_customer())
	if full_name:
		customer.customer_name = full_name
	if mobile:
		customer.nir_mobile = mobile
	customer.save(ignore_permissions=True)
	return {"customer": customer.name, "customer_name": customer.customer_name, "mobile": customer.nir_mobile}


# ---- cart (draft Sales Order)


def find_cart(customer):
	return frappe.db.get_value("Sales Order", {"customer": customer, "docstatus": 0, "nir_is_online_order": 1,
		"nir_online_status": CART}, order_by="modified desc")


def get_cart_doc(create=True):
	customer = get_customer()
	name = find_cart(customer)
	if name:
		return frappe.get_doc("Sales Order", name)
	if not create:
		return None
	settings = get_settings()
	so = frappe.new_doc("Sales Order")
	so.update({
		"customer": customer, "company": settings.company, "order_type": "Shopping Cart", "transaction_date": nowdate(),
		"delivery_date": nowdate(), "selling_price_list": settings.price_list, "taxes_and_charges": settings.taxes_and_charges,
		"currency": "INR", "conversion_rate": 1, "plc_conversion_rate": 1, "price_list_currency": "INR",
		"nir_is_online_order": 1, "nir_online_status": CART, "nir_website_user": website_user(),
		"nir_fulfilment_type": "Home Delivery", "nir_payment_method": "Online", "nir_payment_status": "Unpaid",
	})
	return so


def get_order(name, statuses=None):
	so = frappe.get_doc("Sales Order", name)
	if not so.nir_is_online_order or so.customer != get_customer(create=False):
		frappe.throw(_("Order not found"), frappe.DoesNotExistError)
	if statuses and so.nir_online_status not in statuses:
		frappe.throw(_("Order {0} is {1}").format(so.name, so.nir_online_status))
	return so


def reprice(so, lines=None):
	"""Rebuild the lines so Pricing Rules, schemes and coupons are applied afresh; add the delivery charge."""
	settings = get_settings()
	lines = lines if lines is not None else [(r.item_code, flt(r.qty)) for r in so.items if not r.is_free_item]
	locations = get_locations(so.nir_pincode, so.nir_pickup_store if so.nir_fulfilment_type == "Store Pickup" else None)
	so.set("items", [])
	for item_code, qty in lines:
		if qty <= 0:
			continue
		check_sold_online(item_code)
		uom = frappe.get_cached_value("Item", item_code, "sales_uom") or frappe.get_cached_value("Item", item_code, "stock_uom")
		so.append("items", {"item_code": item_code, "qty": qty, "uom": uom, "delivery_date": so.delivery_date,
			"warehouse": tentative_location(item_code, qty, uom, locations)})
	so.nir_rx_required = int(any(frappe.get_cached_value("Item", r.item_code, "nir_rx_required") for r in so.items))
	so.set("taxes", [])
	so.set_missing_values()
	if so.taxes_and_charges and not so.taxes:
		so.append_taxes_from_master()
	so.calculate_taxes_and_totals()

	charge = 0
	if so.nir_fulfilment_type == "Home Delivery" and flt(settings.delivery_charge) and so.items:
		if not flt(settings.free_delivery_above) or flt(so.grand_total) < flt(settings.free_delivery_above):
			charge = flt(settings.delivery_charge)
	so.nir_delivery_charge = charge
	if charge:
		if not settings.delivery_charge_account:
			frappe.throw(_("Set the Delivery Charge Account in Online Order Settings"))
		so.append("taxes", {"charge_type": "Actual", "account_head": settings.delivery_charge_account,
			"description": DELIVERY_CHARGE_DESCRIPTION, "tax_amount": charge,
			"cost_center": frappe.get_cached_value("Company", so.company, "cost_center")})
		so.calculate_taxes_and_totals()


def tentative_location(item_code, qty, uom, locations):
	"""Nearest location with the stock (final allocation happens when the order is confirmed)."""
	from pharmacy.overrides.pos_billing import uom_factor

	need = flt(qty) * uom_factor(item_code, uom, frappe.get_cached_value("Item", item_code, "stock_uom"))
	fallback = None
	for loc in locations:
		stock = available_qty(item_code, loc.warehouse)
		for leaf, available in sorted(stock.items(), key=lambda kv: -kv[1]):
			if available >= need:
				return leaf
			fallback = fallback or leaf
	if fallback:
		return fallback
	settings = get_settings()
	from pharmacy.online.catalog import sellable_warehouses

	for loc in locations or [frappe._dict(warehouse=settings.dc_warehouse)]:
		leaves = sellable_warehouses(loc.warehouse) if loc.warehouse else []
		if leaves:
			return leaves[0]
	frappe.throw(_("No location can supply {0}").format(item_code))


def save_cart(so):
	so.flags.ignore_permissions = True
	so.save()
	return cart_dict(so)


def cart_dict(so):
	if not so:
		return {"items": [], "grand_total": 0}
	settings = get_settings()
	loyalty_amount = flt(so.loyalty_amount)
	payable = flt(so.rounded_total or so.grand_total) - loyalty_amount
	cod_ok = bool(settings.cod_enabled) and (not flt(settings.cod_max_amount) or payable <= flt(settings.cod_max_amount))
	return {
		"name": so.name, "status": so.nir_online_status,
		"items": [{"item_code": r.item_code, "item_name": r.item_name, "qty": r.qty, "uom": r.uom, "mrp": r.price_list_rate,
			"rate": r.rate, "discount_pct": r.discount_percentage, "amount": r.amount, "free": r.is_free_item,
			"rx_required": cint(frappe.get_cached_value("Item", r.item_code, "nir_rx_required"))} for r in so.items],
		"rx_required": so.nir_rx_required, "coupon_code": so.coupon_code,
		"items_total": flt(so.grand_total) - flt(so.nir_delivery_charge), "delivery_charge": flt(so.nir_delivery_charge),
		"grand_total": flt(so.rounded_total or so.grand_total), "loyalty_points": cint(so.loyalty_points),
		"loyalty_amount": loyalty_amount, "payable": payable, "cod_available": cod_ok,
		"fulfilment_type": so.nir_fulfilment_type, "pincode": so.nir_pincode, "pickup_store": so.nir_pickup_store,
		"shipping_address": so.shipping_address_name, "prescription": so.nir_prescription,
		"customer_prescription": so.nir_customer_prescription, "min_order_value": flt(settings.min_order_value),
	}


@website_api
def get_cart():
	return cart_dict(get_cart_doc(create=False))


@website_api
def add_to_cart(item_code: str, qty: float = 1):
	so = get_cart_doc()
	lines = [(r.item_code, flt(r.qty)) for r in so.items if not r.is_free_item]
	for i, (code, current) in enumerate(lines):
		if code == item_code:
			lines[i] = (code, current + flt(qty))
			break
	else:
		lines.append((item_code, flt(qty)))
	reprice(so, lines)
	return save_cart(so)


@website_api
def update_cart(item_code: str, qty: float):
	"""Set the quantity of a line; 0 removes it."""
	so = get_cart_doc()
	lines = [(r.item_code, flt(qty) if r.item_code == item_code else flt(r.qty)) for r in so.items if not r.is_free_item]
	reprice(so, lines)
	return save_cart(so)


@website_api
def apply_coupon(coupon_code: str | None = None):
	"""Empty code removes the coupon."""
	from erpnext.accounts.doctype.pricing_rule.utils import validate_coupon_code

	so = get_cart_doc(create=False) or frappe.throw(_("Your cart is empty"))
	coupon = None
	if coupon_code:
		coupon = frappe.db.get_value("Coupon Code", {"coupon_code": coupon_code.strip()}) or frappe.throw(_("Invalid coupon code"))
		validate_coupon_code(coupon)
	so.coupon_code = coupon
	reprice(so)
	return save_cart(so)


@website_api
def get_loyalty():
	from erpnext.accounts.doctype.loyalty_program.loyalty_program import get_loyalty_program_details_with_points

	details = get_loyalty_program_details_with_points(get_customer(), company=get_settings().company, silent=True) or {}
	return {"program": details.get("loyalty_program"), "points": cint(details.get("loyalty_points")),
		"value_per_point": flt(details.get("conversion_factor"))}


@website_api
def use_loyalty_points(points: int = 0):
	so = get_cart_doc(create=False) or frappe.throw(_("Your cart is empty"))
	points = cint(points)
	so.loyalty_points, so.loyalty_amount = 0, 0
	if points:
		balance = get_loyalty()
		if not balance["program"]:
			frappe.throw(_("You are not enrolled in a loyalty programme"))
		if points > balance["points"]:
			frappe.throw(_("You have only {0} loyalty points").format(balance["points"]))
		so.loyalty_points = points
		so.loyalty_amount = min(points * balance["value_per_point"], flt(so.grand_total))
	return save_cart(so)


@website_api
def set_delivery(fulfilment_type: str, pincode: str | None = None, pickup_store: str | None = None, address: str | dict | None = None):
	"""Home Delivery with a pincode and address (an Address name or new address fields), or Store Pickup."""
	so = get_cart_doc(create=False) or frappe.throw(_("Your cart is empty"))
	if fulfilment_type not in ("Home Delivery", "Store Pickup"):
		frappe.throw(_("Choose Home Delivery or Store Pickup"))
	so.nir_fulfilment_type = fulfilment_type
	if fulfilment_type == "Store Pickup":
		get_locations(pickup_store=pickup_store)
		so.nir_pickup_store, so.nir_pincode = pickup_store, None
	else:
		address_name = save_address(so.customer, address) if address else so.shipping_address_name
		if address_name:
			so.shipping_address_name = so.customer_address = address_name
			pincode = pincode or frappe.db.get_value("Address", address_name, "pincode")
		if not get_locations(pincode):
			frappe.throw(_("We do not deliver to {0} yet").format(pincode))
		so.nir_pincode, so.nir_pickup_store = pincode, None
	reprice(so)
	return save_cart(so)


def save_address(customer, address):
	address = frappe.parse_json(address) if isinstance(address, str) and address.startswith("{") else address
	if isinstance(address, str):
		if not frappe.db.exists("Dynamic Link", {"parenttype": "Address", "parent": address, "link_doctype": "Customer", "link_name": customer}):
			frappe.throw(_("Address not found"))
		return address
	doc = frappe.get_doc({
		"doctype": "Address", "address_title": address.get("name") or customer, "address_type": "Shipping",
		"address_line1": address.get("address_line1"), "address_line2": address.get("address_line2"), "city": address.get("city"),
		"state": address.get("state"), "pincode": address.get("pincode"), "country": address.get("country") or "India",
		"phone": address.get("phone"), "links": [{"link_doctype": "Customer", "link_name": customer}],
	})
	doc.insert(ignore_permissions=True)
	return doc.name


@website_api
def get_addresses():
	customer = get_customer()
	return frappe.get_all("Address", filters=[["Dynamic Link", "link_doctype", "=", "Customer"], ["Dynamic Link", "link_name", "=", customer]],
		fields=["name", "address_line1", "address_line2", "city", "state", "pincode", "phone"])


@website_api
def get_prescriptions():
	"""The customer's saved prescriptions that are still valid."""
	return frappe.get_all("Customer Prescription", filters={"customer": get_customer(), "valid_upto": (">=", nowdate())},
		fields=["name", "patient_name", "doctor_name", "prescription_date", "valid_upto", "prescription_file"], order_by="prescription_date desc")


@website_api
def attach_prescription(file_url: str | None = None, customer_prescription: str | None = None, patient_name: str | None = None):
	"""A file uploaded with /api/method/upload_file, or one of the customer's saved prescriptions."""
	so = get_cart_doc(create=False) or frappe.throw(_("Your cart is empty"))
	if customer_prescription:
		rx = frappe.db.get_value("Customer Prescription", customer_prescription, ["customer", "valid_upto", "prescription_file", "patient_name"], as_dict=True)
		if not rx or rx.customer != so.customer:
			frappe.throw(_("Prescription not found"))
		if str(rx.valid_upto) < nowdate():
			frappe.throw(_("This prescription has expired; upload a new one"))
		so.nir_customer_prescription, so.nir_prescription = customer_prescription, rx.prescription_file
		patient_name = patient_name or rx.patient_name
	elif file_url:
		if not frappe.db.exists("File", {"file_url": file_url, "owner": website_user()}):
			frappe.throw(_("Upload the prescription first"))
		so.nir_prescription, so.nir_customer_prescription = file_url, None
	so.nir_online_patient_name = patient_name or so.nir_online_patient_name or so.customer_name
	result = save_cart(so)
	if file_url:
		# attached to the order, so the pharmacists who can open the order can open the private file
		frappe.db.set_value("File", {"file_url": file_url, "owner": website_user()},
			{"attached_to_doctype": "Sales Order", "attached_to_name": so.name, "is_private": 1})
	return result


@website_api
def place_order(payment_method: str = "Online"):
	"""Cart becomes the order. Rx orders wait for the pharmacist; the rest go to payment or, for COD, are confirmed."""
	from pharmacy.online.fulfilment import confirm_order

	so = get_cart_doc(create=False) or frappe.throw(_("Your cart is empty"))
	settings = get_settings()
	reprice(so)
	if not so.items:
		frappe.throw(_("Your cart is empty"))
	if flt(settings.min_order_value) and flt(so.grand_total) < flt(settings.min_order_value):
		frappe.throw(_("Minimum order value is {0}").format(frappe.format(settings.min_order_value, "Currency")))
	if so.nir_fulfilment_type == "Home Delivery" and not (so.nir_pincode and so.shipping_address_name):
		frappe.throw(_("Add a delivery address"))
	if so.nir_fulfilment_type == "Store Pickup" and not so.nir_pickup_store:
		frappe.throw(_("Choose a store for pickup"))
	if so.nir_rx_required and not so.nir_prescription:
		frappe.throw(_("Upload a prescription for: {0}").format(", ".join(
			r.item_name for r in so.items if frappe.get_cached_value("Item", r.item_code, "nir_rx_required"))), title=_("Prescription required"))
	if payment_method not in ("Online", "Cash on Delivery"):
		frappe.throw(_("Choose a payment method"))
	if payment_method == "Online" and not settings.payment_gateway_account:
		frappe.throw(_("Online payment is not available right now; choose cash on delivery"))
	if payment_method == "Cash on Delivery" and not cart_dict(so)["cod_available"]:
		frappe.throw(_("Cash on delivery is not available for this order"))

	so.nir_payment_method = payment_method
	so.nir_payment_status = "COD Pending" if payment_method == "Cash on Delivery" else "Unpaid"
	so.nir_placed_on = now_datetime()
	so.po_no = so.po_no or f"WEB-{frappe.generate_hash(length=8).upper()}"
	# provisional: the nearest location; set again once the order is allocated
	hours = min([cint(loc.hours) for loc in get_locations(so.nir_pincode, so.nir_pickup_store)] or [48])
	so.nir_expected_by = expected_by(hours)
	so.delivery_date = so.nir_expected_by.date()
	for row in so.items:
		row.delivery_date = so.delivery_date
	so.nir_review_status = "Not Required"
	so.flags.ignore_permissions = True
	so.save()
	confirm_order(so)
	return order_dict(frappe.get_doc("Sales Order", so.name))


def notify_pharmacists(so):
	from frappe.utils.user import get_users_with_role

	for user in get_users_with_role("Online Order Pharmacist"):
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Sales Order",
			"document_name": so.name, "subject": _("Check prescription for online order {0}").format(so.name)}).insert(ignore_permissions=True)


# ---- orders


def order_dict(so):
	data = cart_dict(so)
	data.update({
		"order_no": so.po_no, "placed_on": so.nir_placed_on, "expected_by": so.nir_expected_by,
		"payment_method": so.nir_payment_method, "payment_status": so.nir_payment_status,
		"prescription_check": so.nir_review_status, "pharmacist_remarks": so.nir_review_remarks if so.nir_review_status == "Rejected" else None,
		"locations": [{"store": f.pharmacy_store or _("Warehouse"), "status": f.status, "invoice": f.sales_invoice} for f in so.nir_fulfilments],
		"can_pay": so.nir_online_status == "Awaiting Payment", "can_cancel": so.nir_online_status in ("Awaiting Payment",),
	})
	return data


@website_api
def my_orders():
	return frappe.get_all("Sales Order", filters={"customer": get_customer(), "nir_is_online_order": 1, "nir_online_status": ("!=", CART)},
		fields=["name", "po_no as order_no", "nir_placed_on as placed_on", "nir_online_status as status", "grand_total",
			"nir_payment_status as payment_status", "nir_expected_by as expected_by"], order_by="nir_placed_on desc")


@website_api
def get_order_details(name: str):
	return order_dict(get_order(name))


@website_api
def cancel_order(name: str, reason: str | None = None):
	"""Customers can cancel until the order is confirmed (allocated and billed afterwards)."""
	so = get_order(name, ("Awaiting Payment",))
	from pharmacy.online.fulfilment import close_order

	close_order(so, "Cancelled", reason or _("Cancelled by customer"))
	return order_dict(frappe.get_doc("Sales Order", so.name))
