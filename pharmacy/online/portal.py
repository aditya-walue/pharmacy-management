"""Public Order Portal API for Frappe Builder and Web Store."""

import json
import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, today, add_days


@frappe.whitelist(allow_guest=True)
def get_available_medicines(search_term=None, limit=50):
	"""Return active sellable medicines with salt, strength, price, dosage form, storage, and category."""
	filters = {
		"disabled": 0,
		"is_sales_item": 1,
		"name": ["not like", "_Test%"],
		"item_group": ["not like", "_Test%"],
	}
	
	fields = [
		"name as item_code",
		"item_name",
		"item_group",
		"nir_salt as generic_name",
		"nir_strength as strength",
		"nir_dosage_form as dosage_form",
		"nir_regulatory_category as category",
		"nir_storage_condition as storage_condition",
		"nir_rx_required as rx_required",
		"stock_uom as uom",
		"valuation_rate as rate",
		"image",
	]

	or_filters = None
	if search_term and search_term.strip():
		t = f"%{search_term.strip()}%"
		or_filters = [
			["name", "like", t],
			["item_name", "like", t],
			["nir_salt", "like", t],
			["brand", "like", t],
			["item_group", "like", t],
		]

	items = frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		limit=cint(limit) or 50,
		order_by="item_name asc",
	)

	clean_items = []
	for it in items:
		if it["item_code"].startswith("138-CMS") or it["item_code"] == "dolo650":
			continue

		price = frappe.db.get_value("Item Price", {"item_code": it["item_code"], "selling": 1}, "price_list_rate")
		if not price:
			price = frappe.db.get_value("Item Price", {"item_code": it["item_code"]}, "price_list_rate")
		if price and flt(price) > 0:
			it["rate"] = round(flt(price), 2)
		elif not it.get("rate") or flt(it["rate"]) <= 0:
			it["rate"] = 45.0
		else:
			it["rate"] = round(flt(it["rate"]), 2)

		clean_items.append(it)

	return clean_items


@frappe.whitelist(allow_guest=True)
def get_stores_and_pincodes():
	"""Return active stores and available pincodes for checkout selection."""
	stores = frappe.get_all(
		"Pharmacy Store",
		filters={"disabled": 0},
		fields=["name", "store_name", "warehouse"],
		order_by="store_name asc",
	)
	pincodes = frappe.get_all(
		"Pharmacy Store Pincode",
		filters={"is_active": 1},
		fields=["pincode", "delivery_hours", "delivery_type", "parent as store"],
		distinct=True,
		limit=50,
	)
	return {"stores": stores, "pincodes": [p["pincode"] for p in pincodes]}


@frappe.whitelist(allow_guest=True)
def submit_online_order(
	customer_name: str,
	mobile_no: str,
	items: str,
	email: str | None = None,
	fulfillment_type: str = "Home Delivery",
	pincode: str | None = None,
	address: str | None = None,
	store: str | None = None,
	payment_method: str = "Razorpay",
	is_patient_special_order: int = 0,
	patient_notes: str | None = None,
	prescription_file: str | None = None,
):
	"""
	Directly places an order from the Web/Builder Portal and creates a Sales Order.
	Accessible to both guests and registered customers.
	"""
	if not customer_name or not customer_name.strip():
		frappe.throw(_("Please provide customer / patient name."))
	if not mobile_no or not mobile_no.strip():
		frappe.throw(_("Please provide a valid contact number."))

	if isinstance(items, str):
		try:
			items_list = json.loads(items)
		except Exception:
			items_list = []
	else:
		items_list = items or []

	if not items_list:
		frappe.throw(_("Your order must contain at least one item."))

	# 1. Find or create Customer
	mobile = mobile_no.strip()
	existing_customer = frappe.db.get_value(
		"Customer",
		{"nir_mobile": mobile},
		"name",
	)
	if not existing_customer:
		existing_customer = frappe.db.get_value(
			"Customer",
			{"customer_name": customer_name.strip()},
			"name",
		)

	if existing_customer:
		customer_doc_name = existing_customer
		if email and not frappe.db.get_value("Customer", existing_customer, "email_id"):
			frappe.db.set_value("Customer", existing_customer, "email_id", email.strip())
	else:
		cust_dict = {
			"doctype": "Customer",
			"customer_name": customer_name.strip(),
			"customer_type": "Individual",
			"nir_mobile": mobile,
			"nir_approval_status": "Approved",
		}
		if email:
			cust_dict["email_id"] = email.strip()
		cust = frappe.get_doc(cust_dict)
		cust.flags.ignore_permissions = True
		cust.insert()
		customer_doc_name = cust.name

	# Determine target warehouse (prioritize retail store warehouse for drug licence compliance)
	default_warehouse = None
	if store:
		default_warehouse = frappe.db.get_value("Pharmacy Store", store, "warehouse")
	if not default_warehouse:
		default_warehouse = frappe.db.get_value(
			"Pharmacy Store",
			{"disabled": 0},
			"warehouse",
		) or frappe.db.get_value(
			"Warehouse",
			{"nir_warehouse_role": "Store", "disabled": 0},
			"name",
		) or frappe.db.get_value("Warehouse", {"is_group": 0, "disabled": 0}, "name")

	# Company
	company = frappe.db.get_value("Warehouse", default_warehouse, "company") if default_warehouse else None
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

	# Build Sales Order items
	so_items = []
	rx_required = 0
	for row in items_list:
		code = row.get("item_code")
		qty = flt(row.get("qty") or 1.0)
		rate = flt(row.get("rate") or 0.0)

		if not rate or rate <= 0:
			rate = flt(frappe.db.get_value("Item", code, "valuation_rate") or 100.0)

		# Check if prescription required
		is_rx = frappe.db.get_value("Item", code, "nir_rx_required")
		if is_rx:
			rx_required = 1

		so_items.append({
			"item_code": code,
			"qty": qty,
			"rate": rate,
			"warehouse": default_warehouse,
			"delivery_date": add_days(today(), 1),
		})

	# 2. Create Sales Order
	so_data = {
		"doctype": "Sales Order",
		"customer": customer_doc_name,
		"company": company,
		"transaction_date": today(),
		"delivery_date": add_days(today(), 1),
		"set_warehouse": default_warehouse,
		"nir_is_online_order": 1,
		"nir_fulfilment_type": fulfillment_type,
		"nir_pincode": pincode,
		"nir_pickup_store": store,
		"nir_payment_method": "Cash on Delivery" if payment_method == "Cash on Delivery" else "Online",
		"nir_payment_status": "COD Pending" if payment_method == "Cash on Delivery" else "Unpaid",
		"nir_online_patient_name": customer_name.strip(),
		"nir_patient_phone": mobile,
		"contact_email": email.strip() if email else None,
		"items": so_items,
	}

	# Patient Special Order fields
	if cint(is_patient_special_order):
		special_store = store or frappe.db.get_value("Pharmacy Store", {"disabled": 0}, "name")
		so_data.update({
			"nir_is_patient_special_order": 1,
			"nir_patient_name": customer_name.strip(),
			"nir_patient_phone": mobile,
			"nir_store": special_store or "",
			"nir_priority": "High",
		})

	if prescription_file:
		so_data["nir_prescription"] = prescription_file

	# Online order lifecycle status
	if rx_required:
		so_data["nir_rx_required"] = 1
		so_data["nir_online_status"] = "Prescription Review"
	elif payment_method == "Razorpay":
		so_data["nir_online_status"] = "Awaiting Payment"
	else:
		so_data["nir_online_status"] = "Confirmed"

	so = frappe.get_doc(so_data)
	so.flags.ignore_permissions = True
	so.insert()

	if patient_notes and patient_notes.strip():
		so.add_comment("Comment", _("Customer Special Instructions: {0}").format(patient_notes.strip()))

	# Dispatch order confirmation email (for COD or Prescription Review; Razorpay sends on payment)
	if so.nir_online_status != "Awaiting Payment":
		try:
			from pharmacy.online.order_notifications import send_order_email
			send_order_email(
				so,
				status_label=so.nir_online_status,
				message_intro=f"Thank you for your order with Pharmacy Store! Your order <strong>#{so.name}</strong> has been received and is currently <strong>{so.nir_online_status}</strong>.",
			)
		except Exception as err:
			frappe.log_error(f"Failed sending order confirmation email for {so.name}: {err}", "Pharmacy Store Email")

	frappe.db.commit()

	return {
		"success": True,
		"sales_order": so.name,
		"grand_total": so.grand_total,
		"status": so.nir_online_status,
		"is_rx_required": bool(rx_required),
		"fulfilment_type": fulfillment_type,
		"payment_method": payment_method,
		"message": _("Sales Order {0} created successfully!").format(so.name),
	}


@frappe.whitelist(allow_guest=True)
def get_razorpay_checkout_details(sales_order: str):
	"""Return key, amount in paise, and order_id for frontend Razorpay checkout modal."""
	so = frappe.get_doc("Sales Order", sales_order)
	api_key = frappe.db.get_single_value("Razorpay Settings", "api_key") or "rzp_test_pharmacy_demo"
	amount_in_paise = int(round(flt(so.grand_total) * 100))
	
	razorpay_order_id = None
	# If Razorpay keys are configured in Razorpay Settings, create live order
	if api_key and not api_key.startswith("rzp_test_pharmacy_demo"):
		try:
			api_secret = frappe.get_single("Razorpay Settings").get_password("api_secret")
			if api_secret:
				import razorpay
				client = razorpay.Client(auth=(api_key, api_secret))
				rz_order = client.order.create({
					"amount": amount_in_paise,
					"currency": "INR",
					"receipt": so.name,
					"notes": {"sales_order": so.name, "customer": so.customer_name}
				})
				razorpay_order_id = rz_order.get("id")
		except Exception as e:
			frappe.log_error(f"Razorpay order creation error: {e}", "Razorpay Checkout")

	return {
		"key": api_key,
		"amount": amount_in_paise,
		"currency": "INR",
		"order_id": razorpay_order_id,
		"sales_order": so.name,
		"customer_name": so.get("nir_patient_name") or so.customer_name,
		"email": so.contact_email or "",
		"phone": so.get("nir_patient_phone") or "",
		"description": f"Pharmacy Store Order #{so.name}"
	}


@frappe.whitelist(allow_guest=True)
def verify_razorpay_payment(sales_order: str, razorpay_payment_id: str, razorpay_order_id: str = None, razorpay_signature: str = None):
	"""
	Verify Razorpay payment, submit Sales Order, and automatically create & submit
	the official GST Sales Invoice with payment recorded.
	"""
	so = frappe.get_doc("Sales Order", sales_order)
	
	# Verify signature if live keys exist
	api_key = frappe.db.get_single_value("Razorpay Settings", "api_key")
	if api_key and not api_key.startswith("rzp_test_pharmacy_demo") and razorpay_signature and razorpay_order_id:
		try:
			api_secret = frappe.get_single("Razorpay Settings").get_password("api_secret")
			import razorpay
			client = razorpay.Client(auth=(api_key, api_secret))
			client.utility.verify_payment_signature({
				"razorpay_order_id": razorpay_order_id,
				"razorpay_payment_id": razorpay_payment_id,
				"razorpay_signature": razorpay_signature
			})
		except Exception as err:
			frappe.throw(_("Razorpay signature verification failed: {0}").format(err))

	# 1. Submit Sales Order if draft
	if so.docstatus == 0:
		so.flags.ignore_permissions = True
		so.submit()

	so.db_set("nir_online_status", "Confirmed")
	so.db_set("nir_payment_status", "Paid")
	so.add_comment("Comment", _("Razorpay online payment authorized successfully. Payment ID: {0}").format(razorpay_payment_id))

	# 2. Automatically create and submit Sales Invoice
	sales_invoice_name = None
	try:
		# Check if an active Sales Invoice already exists for this order
		existing_si = frappe.db.sql("""
			SELECT DISTINCT parent FROM `tabSales Invoice Item`
			WHERE sales_order = %s AND docstatus < 2
			LIMIT 1
		""", (so.name,), as_dict=True)

		if existing_si:
			sales_invoice_name = existing_si[0].parent
			si = frappe.get_doc("Sales Invoice", sales_invoice_name)
			if si.docstatus == 0:
				si.flags.ignore_permissions = True
				si.submit()
		else:
			from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
			si = make_sales_invoice(so.name)
			si.flags.ignore_permissions = True

			# Ensure retail store warehouse is set if current warehouse lacks retail drug licence
			store_wh = frappe.db.get_value("Pharmacy Store", {"disabled": 0}, "warehouse")
			if not si.set_warehouse or "DC" in (si.set_warehouse or ""):
				if store_wh:
					si.set_warehouse = store_wh
					for item in si.items:
						item.warehouse = store_wh

			si.insert(ignore_permissions=True)
			si.submit()
			sales_invoice_name = si.name

		# 3. Create and submit Payment Entry against Sales Invoice
		if sales_invoice_name:
			try:
				from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
				si_doc = frappe.get_doc("Sales Invoice", sales_invoice_name)
				if flt(si_doc.outstanding_amount) > 0:
					pe = get_payment_entry("Sales Invoice", sales_invoice_name)
					pe.reference_no = razorpay_payment_id
					pe.reference_date = today()
					pe.flags.ignore_permissions = True
					pe.insert(ignore_permissions=True)
					pe.submit()
			except Exception as pe_err:
				frappe.log_error(f"Payment Entry auto-creation notice for {sales_invoice_name}: {pe_err}", "Razorpay Payment Entry")

		so.add_comment("Comment", _("Sales Invoice {0} automatically created and submitted via Razorpay payment {1}.").format(sales_invoice_name, razorpay_payment_id))
	except Exception as si_err:
		frappe.log_error(f"Auto Sales Invoice creation failed for {so.name}: {si_err}", "Razorpay Sales Invoice")

	# 4. Send payment & invoice confirmation email
	try:
		from pharmacy.online.order_notifications import send_order_email
		inv_text = f" Official Sales Invoice <strong>#{sales_invoice_name}</strong> has been generated." if sales_invoice_name else ""
		send_order_email(
			so,
			status_label="Payment Received (Confirmed)",
			message_intro=f"Thank you! Your online payment of <strong>INR {so.grand_total:.2f}</strong> for Order <strong>#{so.name}</strong> was received via Razorpay (Ref: {razorpay_payment_id}).{inv_text} Your order is now <strong>Confirmed</strong>."
		)
	except Exception as err:
		frappe.log_error(f"Error sending payment email for {so.name}: {err}", "Razorpay Email")

	frappe.db.commit()

	return {
		"success": True,
		"sales_order": so.name,
		"sales_invoice": sales_invoice_name,
		"payment_id": razorpay_payment_id,
		"status": "Confirmed",
		"message": _("Payment verified and Sales Invoice {0} created successfully for order {1}!").format(sales_invoice_name or "", so.name)
	}


@frappe.whitelist(allow_guest=True)
def get_customer_orders(identifier: str = None):
	"""
	Return list of online Sales Orders for a customer by phone number, email address, or order ID.
	Includes item details, live status, and linked Sales Invoice information.
	"""
	if not identifier or not identifier.strip():
		if frappe.session.user and frappe.session.user != "Guest":
			identifier = frappe.session.user
		else:
			return {
				"success": False,
				"orders": [],
				"message": _("Please enter your registered phone number or email address to view orders.")
			}

	ident = identifier.strip()

	# Find matching customer records
	matching_customers = frappe.db.sql_list("""
		SELECT name FROM `tabCustomer`
		WHERE nir_mobile = %s OR email_id = %s OR name = %s
	""", (ident, ident, ident))

	# Also search with stripped phone digits
	clean_digits = "".join(ch for ch in ident if ch.isdigit())
	if clean_digits and len(clean_digits) >= 10:
		phone_suffix = clean_digits[-10:]
		more_customers = frappe.db.sql_list("""
			SELECT name FROM `tabCustomer`
			WHERE nir_mobile LIKE %s
		""", (f"%{phone_suffix}%",))
		for c in more_customers:
			if c not in matching_customers:
				matching_customers.append(c)

	# Build query conditions
	conditions = ["(name = %(ident)s OR contact_email = %(ident)s OR nir_patient_phone = %(ident)s"]
	values = {"ident": ident}

	if clean_digits and len(clean_digits) >= 10:
		conditions.append("nir_patient_phone LIKE %(phone_like)s")
		values["phone_like"] = f"%{clean_digits[-10:]}%"

	if matching_customers:
		conditions.append("customer IN %(customers)s")
		values["customers"] = tuple(matching_customers)

	where_clause = " OR ".join(conditions) + ")"

	orders = frappe.db.sql(f"""
		SELECT
			name,
			transaction_date,
			delivery_date,
			customer_name,
			contact_email,
			nir_patient_phone,
			nir_online_patient_name,
			nir_is_online_order,
			nir_online_status,
			nir_payment_method,
			nir_payment_status,
			nir_fulfilment_type,
			nir_pickup_store,
			nir_pincode,
			nir_prescription,
			grand_total,
			docstatus
		FROM `tabSales Order`
		WHERE {where_clause}
		ORDER BY creation DESC
		LIMIT 25
	""", values, as_dict=True)

	for o in orders:
		o["transaction_date"] = str(o.transaction_date) if o.transaction_date else ""
		o["delivery_date"] = str(o.delivery_date) if o.delivery_date else ""
		o["grand_total"] = flt(o.grand_total)

		# Fetch line items
		o["items"] = frappe.db.sql("""
			SELECT
				item_code,
				item_name,
				qty,
				rate,
				amount,
				uom
			FROM `tabSales Order Item`
			WHERE parent = %s
			ORDER BY idx ASC
		""", (o.name,), as_dict=True)

		for it in o["items"]:
			it["qty"] = flt(it["qty"])
			it["rate"] = flt(it["rate"])
			it["amount"] = flt(it["amount"])
			# Enrich with clinical information
			med_info = frappe.db.get_value(
				"Item",
				it["item_code"],
				["nir_salt", "nir_strength", "nir_dosage_form", "nir_storage_condition"],
				as_dict=True
			)
			if med_info:
				it["generic_name"] = med_info.get("nir_salt") or ""
				it["strength"] = med_info.get("nir_strength") or ""
				it["dosage_form"] = med_info.get("nir_dosage_form") or ""
				it["storage_condition"] = med_info.get("nir_storage_condition") or ""

		# Check for linked Sales Invoice
		si_data = frappe.db.sql("""
			SELECT DISTINCT parent
			FROM `tabSales Invoice Item`
			WHERE sales_order = %s AND docstatus < 2
			ORDER BY creation DESC
			LIMIT 1
		""", (o.name,), as_dict=True)

		if si_data:
			si_doc = frappe.get_doc("Sales Invoice", si_data[0].parent)
			o["sales_invoice"] = {
				"name": si_doc.name,
				"posting_date": str(si_doc.posting_date),
				"status": si_doc.status,
				"grand_total": flt(si_doc.grand_total),
				"outstanding_amount": flt(si_doc.outstanding_amount),
				"docstatus": si_doc.docstatus,
			}
		else:
			o["sales_invoice"] = None

	return {
		"success": True,
		"orders": orders,
		"count": len(orders)
	}


@frappe.whitelist(allow_guest=True)
def get_order_invoice_details(sales_invoice: str):
	"""
	Return formatted invoice details for modal receipt or customer print view.
	"""
	if not sales_invoice:
		frappe.throw(_("Invoice number required."))

	si = frappe.get_doc("Sales Invoice", sales_invoice)
	company = si.company or frappe.defaults.get_user_default("Company")
	company_doc = frappe.get_doc("Company", company) if company else None

	items = []
	for it in si.items:
		items.append({
			"item_code": it.item_code,
			"item_name": it.item_name,
			"batch_no": it.batch_no or "-",
			"qty": flt(it.qty),
			"uom": it.uom,
			"rate": flt(it.rate),
			"amount": flt(it.amount),
		})

	taxes = []
	for tx in (si.taxes or []):
		taxes.append({
			"description": tx.description,
			"tax_amount": flt(tx.tax_amount),
		})

	return {
		"success": True,
		"invoice": {
			"name": si.name,
			"posting_date": str(si.posting_date),
			"due_date": str(si.due_date) if si.due_date else "",
			"status": si.status,
			"company": company,
			"company_gstin": company_doc.get("tax_id") if company_doc else "",
			"customer_name": si.customer_name,
			"patient_name": si.get("nir_patient_name") or si.customer_name,
			"net_total": flt(si.net_total),
			"total_taxes_and_charges": flt(si.total_taxes_and_charges),
			"grand_total": flt(si.grand_total),
			"outstanding_amount": flt(si.outstanding_amount),
			"items": items,
			"taxes": taxes,
		}
	}
