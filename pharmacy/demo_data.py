"""Realistic pharmacy test catalogue for a development site.

    bench --site pharmacy.local execute pharmacy.demo_data.create_demo_items --kwargs '{"company": "_Test Pharmacy"}'

Idempotent: existing records are left as they are. Brands, salts and manufacturers are real products sold in
India; prices are indicative and barcodes are generated (valid EAN-13 check digits, not the products' real codes).
"""

import frappe
from frappe.utils import flt

UOMS = ("Bottle", "Vial", "Pen", "Tube", "Capsule", "Can")
EAN_PREFIX = "890999"  # 890 = India; the rest marks these as test codes

# code, name, brand, item group, category, storage, salt, strength, dosage form, manufacturer, marketer,
# stock UOM, pack UOM, units per pack, packs per box, HSN, GST %, MRP per pack, PTR per pack, NPPA, ABC, loose sale
ITEMS = [
	("DOLO-650", "Dolo 650 Tablet", "Dolo", "OTC", "OTC", "Ambient", "Paracetamol", "650 mg", "Tablet", "Micro Labs", "Micro Labs", "Tablet", "Strip", 15, 10, "30049099", 5, 33.60, 24.00, 1, "A", 1),
	("CALPOL-500", "Calpol 500 Tablet", "Calpol", "OTC", "OTC", "Ambient", "Paracetamol", "500 mg", "Tablet", "GSK", "Haleon", "Tablet", "Strip", 15, 10, "30049099", 5, 16.50, 11.80, 1, "A", 1),
	("CROCIN-ADV-500", "Crocin Advance 500 Tablet", "Crocin", "OTC", "OTC", "Ambient", "Paracetamol", "500 mg", "Tablet", "GSK", "Haleon", "Tablet", "Strip", 15, 10, "30049099", 5, 18.00, 12.80, 1, "A", 1),
	("NIR-PCM-500", "Nirmal Paracetamol 500 Tablet", "Nirmal", "Private Label", "OTC", "Ambient", "Paracetamol", "500 mg", "Tablet", "Nirmal Healthcare", "Nirmal Pharmacy", "Tablet", "Strip", 10, 10, "30049099", 5, 10.00, 5.50, 1, "B", 1),
	("AUGMENTIN-625", "Augmentin 625 Duo Tablet", "Augmentin", "Schedule H", "Schedule H", "Below 25C", "Amoxicillin + Clavulanic Acid", "500 mg + 125 mg", "Tablet", "GSK", "GSK", "Tablet", "Strip", 10, 10, "30049099", 5, 223.40, 160.00, 1, "A", 1),
	("AZITHRAL-500", "Azithral 500 Tablet", "Azithral", "Schedule H", "Schedule H", "Ambient", "Azithromycin", "500 mg", "Tablet", "Alembic", "Alembic", "Tablet", "Strip", 5, 10, "30049099", 5, 119.50, 85.00, 1, "A", 1),
	("PAN-40", "Pan 40 Tablet", "Pan", "Schedule H", "Schedule H", "Ambient", "Pantoprazole", "40 mg", "Tablet", "Alkem", "Alkem", "Tablet", "Strip", 15, 10, "30049099", 5, 155.00, 110.00, 0, "A", 1),
	("GLYCOMET-500", "Glycomet 500 SR Tablet", "Glycomet", "Schedule H", "Schedule H", "Ambient", "Metformin", "500 mg", "Tablet", "USV", "USV", "Tablet", "Strip", 20, 10, "30049099", 5, 34.00, 24.50, 1, "A", 1),
	("TELMA-40", "Telma 40 Tablet", "Telma", "Schedule H", "Schedule H", "Ambient", "Telmisartan", "40 mg", "Tablet", "Glenmark", "Glenmark", "Tablet", "Strip", 15, 10, "30049099", 5, 245.00, 175.00, 1, "B", 1),
	("ATORVA-10", "Atorva 10 Tablet", "Atorva", "Schedule H", "Schedule H", "Ambient", "Atorvastatin", "10 mg", "Tablet", "Zydus", "Zydus", "Tablet", "Strip", 15, 10, "30049099", 5, 125.00, 89.00, 1, "B", 1),
	("ECOSPRIN-75", "Ecosprin 75 Tablet", "Ecosprin", "Schedule H", "Schedule H", "Ambient", "Aspirin", "75 mg", "Tablet", "USV", "USV", "Tablet", "Strip", 14, 10, "30049099", 5, 5.20, 3.70, 1, "B", 1),
	("ZIFI-200", "Zifi 200 Tablet", "Zifi", "Schedule H1", "Schedule H1", "Ambient", "Cefixime", "200 mg", "Tablet", "FDC", "FDC", "Tablet", "Strip", 10, 10, "30049099", 5, 109.00, 78.00, 1, "B", 1),
	("LEVOFLOX-500", "Levoflox 500 Tablet", "Levoflox", "Schedule H1", "Schedule H1", "Ambient", "Levofloxacin", "500 mg", "Tablet", "Cipla", "Cipla", "Tablet", "Strip", 10, 10, "30049099", 5, 105.00, 75.00, 1, "C", 1),
	("ALPRAX-025", "Alprax 0.25 Tablet", "Alprax", "NDPS", "NDPS", "Ambient", "Alprazolam", "0.25 mg", "Tablet", "Torrent", "Torrent", "Tablet", "Strip", 15, 10, "30049099", 5, 33.50, 23.90, 1, "C", 0),
	("RIVOTRIL-05", "Rivotril 0.5 Tablet", "Rivotril", "NDPS", "NDPS", "Ambient", "Clonazepam", "0.5 mg", "Tablet", "Abbott", "Abbott", "Tablet", "Strip", 10, 10, "30049099", 5, 58.00, 41.00, 0, "C", 0),
	("ADDWIZE-10", "Addwize 10 Tablet", "Addwize", "Schedule X", "Schedule X", "Ambient", "Methylphenidate", "10 mg", "Tablet", "Sun Pharma", "Sun Pharma", "Tablet", "Strip", 10, 10, "30049099", 5, 132.00, 94.00, 0, "C", 0),
	("HUMINSULIN-R-40", "Huminsulin R 40 IU/ml Injection 10 ml", "Huminsulin", "Schedule H", "Schedule H", "2-8C", "Human Insulin (Regular)", "40 IU/ml", "Injection", "Eli Lilly", "Lupin", "Vial", "Vial", 1, 10, "30043110", 5, 165.00, 118.00, 1, "A", 0),
	("LANTUS-SOLOSTAR", "Lantus SoloStar 100 IU/ml Pen 3 ml", "Lantus", "Schedule H", "Schedule H", "2-8C", "Insulin Glargine", "100 IU/ml", "Injection", "Sanofi", "Sanofi", "Pen", "Pen", 1, 5, "30043110", 5, 728.00, 520.00, 0, "A", 0),
	("REVITAL-H", "Revital H Capsule", "Revital", "Wellness", "FSSAI", "Ambient", None, None, "Capsule", "Sun Pharma", "Sun Pharma", "Capsule", "Strip", 10, 3, "21069099", 18, 110.00, 78.00, 0, "B", 1),
	("ENSURE-400", "Ensure Vanilla Powder 400 g", "Ensure", "FMCG", "FSSAI", "Ambient", None, "400 g", "Powder", "Abbott", "Abbott", "Can", "Can", 1, 12, "21069099", 5, 735.00, 600.00, 0, "B", 0),
	("CETAPHIL-GSC-125", "Cetaphil Gentle Skin Cleanser 125 ml", "Cetaphil", "Cosmetics", "Cosmetic", "Ambient", None, "125 ml", "Other", "Galderma", "Galderma", "Bottle", "Bottle", 1, 24, "34013090", 18, 399.00, 300.00, 0, "C", 0),
	("VOLINI-30", "Volini Gel 30 g", "Volini", "OTC", "OTC", "Ambient", "Diclofenac + Methyl Salicylate", "1.16% w/w", "Gel", "Sun Pharma", "Sun Pharma", "Tube", "Tube", 1, 20, "30049099", 5, 125.00, 90.00, 0, "B", 0),
	("DETTOL-250", "Dettol Antiseptic Liquid 250 ml", "Dettol", "FMCG", "OTC", "Ambient", "Chloroxylenol", "4.8% w/v", "Other", "Reckitt", "Reckitt", "Bottle", "Bottle", 1, 24, "38089400", 18, 132.00, 100.00, 0, "B", 0),
	("DISPOVAN-5ML", "Dispovan Syringe 5 ml with Needle", "Dispovan", "Surgical", "OTC", "Ambient", None, "5 ml", "Device", "Hindustan Syringes", "HMD", "Nos", "Box", 100, 10, "90183100", 5, 1200.00, 650.00, 0, "C", 1),
	("VENUS-N95", "Venus V-4400 N95 Mask", "Venus", "Surgical", "OTC", "Ambient", None, None, "Device", "Venus Safety", "Venus Safety", "Nos", "Box", 20, 10, "63079090", 5, 1980.00, 1100.00, 0, "C", 1),
]


def create_demo_items(company="_Test Pharmacy"):
	templates = {
		flt(t.gst_rate): t.name
		for t in frappe.get_all(
			"Item Tax Template", filters={"company": company, "disabled": 0}, fields=["name", "gst_rate"], order_by="name"
		)
		if "GST" in t.name
	}
	for uom in UOMS:
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": 1}).insert(ignore_permissions=True)

	created = []
	for n, row in enumerate(ITEMS, start=1):
		(code, name, brand, group, category, storage, salt, strength, form, maker, marketer,
		 stock_uom, pack_uom, units, packs_per_box, hsn, gst, mrp, ptr, nppa, abc, loose) = row
		ensure("Brand", brand, {"brand": brand})
		ensure("Manufacturer", maker, {"short_name": maker, "full_name": maker, "country": "India"})
		if salt:
			ensure("Salt", salt, {"salt_name": salt})
		if frappe.db.exists("Item", code):
			continue

		uoms = [{"uom": stock_uom, "conversion_factor": 1}]
		if pack_uom != stock_uom:
			uoms.append({"uom": pack_uom, "conversion_factor": units})
		if pack_uom != "Box":
			uoms.append({"uom": "Box", "conversion_factor": units * packs_per_box})

		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"description": name,
				"brand": brand,
				"item_group": group,
				"stock_uom": stock_uom,
				"purchase_uom": "Box",
				"sales_uom": pack_uom,
				"uoms": uoms,
				"is_stock_item": 1,
				"gst_hsn_code": hsn,
				"valuation_rate": flt(ptr) / units,
				"taxes": [{"item_tax_template": templates[flt(gst)]}] if flt(gst) in templates else [],
				"barcodes": [{"barcode": ean13(n), "barcode_type": "EAN", "uom": pack_uom}],
				"nir_regulatory_category": category,
				"nir_storage_condition": storage,
				"nir_salt": salt,
				"nir_strength": strength,
				"nir_dosage_form": form,
				"nir_manufacturer": maker,
				"nir_marketer": marketer,
				"nir_nppa_controlled": nppa,
				"nir_abc_class": abc,
				"nir_loose_sale": loose,
				"nir_approval_status": "Approved",
			}
		).insert(ignore_permissions=True)

		for price_list, rate in (("Standard Buying", ptr), ("Standard Selling", mrp)):
			frappe.get_doc(
				{"doctype": "Item Price", "price_list": price_list, "item_code": code, "uom": pack_uom,
				 "price_list_rate": rate, "nir_approval_status": "Approved"}
			).insert(ignore_permissions=True)

		if nppa:
			# ceiling per stock unit before GST, a little above this pack's MRP so current batches comply
			frappe.get_doc(
				{"doctype": "NPPA Ceiling Price", "item": code, "valid_from": "2026-04-01",
				 "ceiling_price": round(flt(mrp) / units / (1 + gst / 100) * 1.03, 2)}
			).insert(ignore_permissions=True)
		created.append(code)

	frappe.db.commit()
	return created


def ensure(doctype, name, values):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def ean13(n):
	digits = f"{EAN_PREFIX}{n:06d}"
	total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(digits))
	return digits + str((10 - total % 10) % 10)


# Purchase Suggestion demo: a DC serving two stores, suppliers with lead times and MOQs, opening DC stock,
# 30 days of store sales and an online order.
#
#     bench --site pharmacy.local execute pharmacy.demo_data.create_purchase_suggestion_data

SUPPLIERS = {
	# name: (lead time days, licence forms)
	"Apex Pharma Distributors": (3, ("20B", "21B", "20G", "FSSAI")),
	"Coldline Biologicals": (5, ("20B", "21B")),
	"Wellness Wholesale": (7, ("20B", "FSSAI")),
}
PREFERRED = {"HUMINSULIN-R-40": "Coldline Biologicals", "LANTUS-SOLOSTAR": "Coldline Biologicals",
	"REVITAL-H": "Wellness Wholesale", "ENSURE-400": "Wellness Wholesale", "CETAPHIL-GSC-125": "Wellness Wholesale",
	"DETTOL-250": "Wellness Wholesale"}
# item: opening DC stock in stock units (low stock → suggestion, high → none)
DC_STOCK = {"DOLO-650": 300, "CALPOL-500": 2000, "AUGMENTIN-625": 40, "PAN-40": 150, "GLYCOMET-500": 2400,
	"TELMA-40": 60, "ZIFI-200": 0, "HUMINSULIN-R-40": 4, "ENSURE-400": 6, "DETTOL-250": 48}
# item: average units sold per day per store
DAILY_SALES = {"DOLO-650": 45, "CALPOL-500": 20, "AUGMENTIN-625": 8, "AZITHRAL-500": 5, "PAN-40": 30, "GLYCOMET-500": 40,
	"TELMA-40": 15, "ATORVA-10": 15, "ZIFI-200": 6, "ALPRAX-025": 3, "HUMINSULIN-R-40": 1, "ENSURE-400": 1,
	"CETAPHIL-GSC-125": 1, "DETTOL-250": 2, "VOLINI-30": 1}
LAYOUT = [
	# bin under the DC: name, zone type, storage condition
	("DC Receiving", "Receiving", "Ambient"),
	("DC General A1", "General", "Ambient"),
	("DC General Cool", "General", "Below 25C"),
	("DC Cold Room", "Cold Room", "2-8C"),
	("DC Cage", "Scheduled Drug Cage", "Ambient"),
	("DC FMCG", "FMCG", "Ambient"),
	("DC Quarantine", "Quarantine", "Ambient"),
	("DC Cold Quarantine", "Quarantine", "2-8C"),
]


def create_purchase_suggestion_data(company="_Test Pharmacy", days=30):
	from frappe.utils import add_days, today

	abbr = frappe.db.get_value("Company", company, "abbr")
	root = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ("is", "not set")})
	dc = warehouse(f"Main DC", abbr, company, root, is_group=1, role="DC", gstin="27AAAAA0000A1Z5")
	bins = {name: warehouse(name, abbr, company, dc, zone=zone, condition=cond) for name, zone, cond in LAYOUT}
	stores = [warehouse(name, abbr, company, root, role="Store") for name in ("Store Andheri", "Store Bandra")]

	for form in ("20B", "21B", "20G", "FSSAI"):
		licence("Warehouse", dc, form)
	for store in stores:
		for form in ("20", "21", "20F", "FSSAI"):
			licence("Warehouse", store, form)
		name = store.split(" - ")[0]
		if not frappe.db.exists("Pharmacy Store", name):
			frappe.get_doc({"doctype": "Pharmacy Store", "store_name": name, "warehouse": store, "serving_warehouse": dc,
				"route": "Route West", "store_grade": "A", "gstin": "27AAAAA0000A1Z5",
				"nir_approval_status": "Approved"}).insert(ignore_permissions=True)
		# maker-checker disables new stores until approved; demo data is pre-approved
		frappe.db.set_value("Pharmacy Store", name, {"disabled": 0, "nir_approval_status": "Approved"})

	for supplier, (lead, forms) in SUPPLIERS.items():
		if not frappe.db.exists("Supplier", supplier):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier, "supplier_type": "Company",
				"supplier_group": "Local", "nir_lead_time_days": lead, "nir_approval_status": "Approved"}).insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", supplier, {"disabled": 0, "nir_lead_time_days": lead})
		for form in forms:
			licence("Supplier", supplier, form)

	# preferred supplier, MOQ (one box) and last purchase rate per stock unit from the catalogue
	for row in ITEMS:
		code, units, packs_per_box, ptr = row[0], row[13], row[14], row[18]
		frappe.db.set_value("Item", code, {
			"nir_preferred_supplier": PREFERRED.get(code, "Apex Pharma Distributors"),
			"min_order_qty": units * packs_per_box if row[12] != "Box" else units,
			"last_purchase_rate": flt(ptr) / units,
		})

	if not frappe.db.exists("Supplier Scheme", {"supplier": "Apex Pharma Distributors", "item_code": "DOLO-650"}):
		frappe.get_doc({"doctype": "Supplier Scheme", "supplier": "Apex Pharma Distributors", "scheme_name": "Dolo 10+1",
			"is_active": 1, "scheme_type": "Free Goods", "item_code": "DOLO-650", "min_order_qty": 450,
			"free_goods_ratio": 0.1, "valid_from": add_days(today(), -60), "valid_upto": add_days(today(), 120)}).insert(ignore_permissions=True)

	opening_stock(company, bins)
	store_sales(company, stores, days)
	online_order(company, bins["DC FMCG"])
	frappe.db.commit()
	return {"dc": dc, "stores": stores}


def warehouse(name, abbr, company, parent, is_group=0, role=None, zone=None, condition=None, gstin=None):
	full = f"{name} - {abbr}"
	if not frappe.db.exists("Warehouse", full):
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": name, "company": company, "parent_warehouse": parent,
			"is_group": is_group, "nir_warehouse_role": role, "nir_zone_type": zone, "nir_storage_condition": condition,
			"nir_gstin": gstin}).insert(ignore_permissions=True)
	return full


def licence(party_type, party, form):
	if not frappe.db.exists("Drug Licence", {"party_type": party_type, "party": party, "licence_form": form}):
		frappe.get_doc({"doctype": "Drug Licence", "party_type": party_type, "party": party, "licence_form": form,
			"licence_no": f"DEMO-{form}-{abs(hash(party)) % 100000:05d}", "valid_from": "2025-01-01",
			"valid_upto": "2028-12-31"}).insert(ignore_permissions=True)


def opening_stock(company, bins):
	"""Opening stock at the DC in the right zone for each item, one batch each."""
	from frappe.utils import add_days, today

	if frappe.db.exists("Bin", {"warehouse": bins["DC General A1"], "item_code": "DOLO-650", "actual_qty": (">", 0)}):
		return
	rows = []
	for code, qty in DC_STOCK.items():
		if not qty:
			continue
		row = next(r for r in ITEMS if r[0] == code)
		category, storage, units, mrp, ptr = row[4], row[5], row[13], row[17], row[18]
		if category in ("Schedule X", "NDPS"):
			zone = "DC Cage"
		elif storage == "2-8C":
			zone = "DC Cold Room"
		elif row[3] in ("FMCG", "Cosmetics", "Wellness"):
			zone = "DC FMCG"
		else:
			zone = "DC General Cool" if storage == "Below 25C" else "DC General A1"
		batch_id = f"{code}-DEMO1"
		if not frappe.db.exists("Batch", batch_id):
			frappe.get_doc({"doctype": "Batch", "batch_id": batch_id, "item": code, "supplier_batch_no": "DEMO1",
				"manufacturing_date": add_days(today(), -60), "expiry_date": add_days(today(), 700),
				"nir_mrp": mrp, "nir_mrp_uom": row[12]}).insert(ignore_permissions=True)
		rows.append({"item_code": code, "warehouse": bins[zone], "qty": qty, "valuation_rate": flt(ptr) / units,
			"batch_no": batch_id, "use_serial_batch_fields": 1})
	# opening stock posts against a balance-sheet account, not stock adjustment
	opening_account = frappe.db.get_value("Account", {"company": company, "account_name": "Temporary Opening", "is_group": 0})
	reco = frappe.get_doc({"doctype": "Stock Reconciliation", "company": company, "purpose": "Opening Stock",
		"expense_account": opening_account, "remarks": "Demo DC opening stock", "items": rows})
	reco.insert(ignore_permissions=True)
	reco.submit()


def walk_in_customer():
	name = "Walk-in Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_group": "Individual",
			"territory": "India", "nir_approval_status": "Approved"}).insert(ignore_permissions=True)
	# maker-checker disables new parties until approved; demo data is pre-approved
	frappe.db.set_value("Customer", name, {"disabled": 0, "nir_approval_status": "Approved"})
	return name


def store_sales(company, stores, days):
	"""One invoice per store per day for the last N days (stock not updated; demand history only)."""
	from frappe.utils import add_days, today

	customer = walk_in_customer()
	if frappe.db.exists("Sales Invoice", {"customer": customer, "remarks": ("like", "Demo store sales%"), "docstatus": 1}):
		return
	for day in range(1, days + 1):
		date = add_days(today(), -day)
		for n, store in enumerate(stores):
			items = [
				{"item_code": code, "qty": max(1, round(rate * (0.7 + 0.6 * ((day * 7 + n * 3 + i) % 5) / 4))),
				 "uom": frappe.db.get_value("Item", code, "stock_uom"), "warehouse": store}
				for i, (code, rate) in enumerate(DAILY_SALES.items())
			]
			invoice = frappe.get_doc({"doctype": "Sales Invoice", "company": company, "customer": customer,
				"posting_date": date, "set_posting_time": 1, "due_date": date, "update_stock": 0,
				"nir_prescription": "/files/demo-prescription.pdf", "nir_doctor_name": "Dr. A. Sharma", "nir_doctor_reg_no": "MMC-12345",
				"remarks": f"Demo store sales {date}", "items": items})
			invoice.insert(ignore_permissions=True)
			invoice.submit()


def online_order(company, fmcg_bin):
	"""An open online order fulfilled from the DC (FSSAI / cosmetic items need no drug licence)."""
	from frappe.utils import add_days, today

	customer = walk_in_customer()
	if frappe.db.exists("Sales Order", {"customer": customer, "docstatus": 1, "po_no": "DEMO-ONLINE"}):
		return
	order = frappe.get_doc({"doctype": "Sales Order", "company": company, "customer": customer, "transaction_date": today(),
		"delivery_date": add_days(today(), 2), "po_no": "DEMO-ONLINE", "nir_is_patient_special_order": 0,
		"items": [{"item_code": "ENSURE-400", "qty": 12, "warehouse": fmcg_bin, "delivery_date": add_days(today(), 2)},
			{"item_code": "CETAPHIL-GSC-125", "qty": 10, "warehouse": fmcg_bin, "delivery_date": add_days(today(), 2)}]})
	order.insert(ignore_permissions=True)
	order.submit()


# POS demo: stock with several batches at Store Andheri (incl. a recalled and an expired batch), POS Profiles,
# an MRP-inclusive tax template, customer types, promotions and a few sample bills.
#
#     bench --site pharmacy.local execute pharmacy.demo_data.create_pos_test_data

# item: [(batch suffix, days to expiry, qty in stock units)] — the first batch expires first (FEFO default)
STORE_STOCK = {
	"DOLO-650": [("A1", 75, 150), ("A2", 420, 300)],
	"CALPOL-500": [("A1", 300, 225)],
	"CROCIN-ADV-500": [("A1", 360, 150)],
	"NIR-PCM-500": [("A1", 500, 200)],
	"PAN-40": [("A1", 90, 75), ("A2", 540, 150)],
	"AUGMENTIN-625": [("A1", 200, 60)],
	"AZITHRAL-500": [("RC", 300, 25), ("A2", 330, 25)],
	"GLYCOMET-500": [("EX", -5, 40), ("A2", 400, 200)],
	"ALPRAX-025": [("A1", 400, 60)],
	"ENSURE-400": [("A1", 250, 6)],
	"CETAPHIL-GSC-125": [("A1", 600, 6)],
	"VOLINI-30": [("A1", 400, 10)],
	"DETTOL-250": [("A1", 700, 12)],
}
CUSTOMERS = {"Mr. R. Iyer": "Senior Citizen", "Pharmacy Staff Member": "Staff"}
PROMOTIONS = [
	# title, item group, customer group, discount %, valid for days (None = always), priority (higher wins)
	("Senior Citizen 5%", "All Item Groups", "Senior Citizen", 5, None, "1"),
	("Staff 10%", "All Item Groups", "Staff", 10, None, "2"),
	("OTC Week 10%", "OTC", None, 10, 14, "3"),
	("Own Label 15%", "Private Label", None, 15, None, "4"),
]


def create_pos_test_data(company="_Test Pharmacy"):
	from frappe.utils import add_days, now_datetime, today

	create_purchase_suggestion_data(company)  # DC, stores, licences and approved masters
	abbr = frappe.db.get_value("Company", company, "abbr")
	store = f"Store Andheri - {abbr}"
	# stores are air-conditioned: ambient and below-25°C items only (no cold-chain stock here)
	frappe.db.set_value("Warehouse", store, "nir_storage_condition", "Below 25C")
	frappe.db.set_value("Warehouse", f"Store Bandra - {abbr}", "nir_storage_condition", "Below 25C")

	store_opening_stock(company, store)
	recall_hold(company, "AZITHRAL-500-RC")
	taxes = inclusive_tax_template(company, abbr)
	walk_in = walk_in_customer()
	for name, group in CUSTOMERS.items():
		ensure("Customer Group", group, {"customer_group_name": group, "parent_customer_group": "All Customer Groups"})
		if not frappe.db.exists("Customer", name):
			frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_group": group, "territory": "India",
				"nir_approval_status": "Approved"}).insert(ignore_permissions=True)
		frappe.db.set_value("Customer", name, {"disabled": 0, "nir_approval_status": "Approved"})

	for title, group, customer_group, pct, days, priority in PROMOTIONS:
		existing = frappe.db.get_value("Pricing Rule", {"title": title})
		if existing:
			frappe.db.set_value("Pricing Rule", existing, "priority", priority)
			continue
		frappe.get_doc({"doctype": "Pricing Rule", "title": title, "apply_on": "Item Group", "selling": 1,
			"price_or_product_discount": "Price", "rate_or_discount": "Discount Percentage", "discount_percentage": pct,
			"company": company, "item_groups": [{"item_group": group}],
			"applicable_for": "Customer Group" if customer_group else "", "customer_group": customer_group,
			"valid_from": add_days(today(), -2) if days else None, "valid_upto": add_days(today(), days) if days else None,
			"priority": priority}).insert(ignore_permissions=True)

	profiles = {}
	for name in ("Store Andheri", "Store Bandra"):
		profile = f"{name} POS"
		if not frappe.db.exists("POS Profile", profile):
			frappe.get_doc({"doctype": "POS Profile", "__newname": profile, "company": company,
				"warehouse": f"{name} - {abbr}", "customer": walk_in, "selling_price_list": "Standard Selling",
				"currency": "INR", "update_stock": 1, "taxes_and_charges": taxes,
				"write_off_account": f"Write Off - {abbr}", "write_off_cost_center": f"Main - {abbr}",
				"cost_center": f"Main - {abbr}", "write_off_limit": 1,
				"payments": [{"mode_of_payment": "Cash", "default": 1}],
				"applicable_for_users": [{"user": "Administrator", "default": 1 if name == "Store Andheri" else 0}]}).insert(ignore_permissions=True)
		profiles[name] = profile

	if not frappe.db.exists("POS Opening Entry", {"pos_profile": profiles["Store Andheri"], "docstatus": 1, "status": "Open"}):
		opening = frappe.get_doc({"doctype": "POS Opening Entry", "company": company, "pos_profile": profiles["Store Andheri"],
			"user": "Administrator", "period_start_date": now_datetime(), "posting_date": today(),
			"balance_details": [{"mode_of_payment": "Cash", "opening_amount": 500}]})
		opening.insert(ignore_permissions=True)
		opening.submit()

	bills = sample_bills(company, profiles["Store Andheri"], store, walk_in, taxes)
	frappe.db.commit()
	return {"profiles": list(profiles.values()), "sample_bills": bills}


def store_opening_stock(company, store):
	from frappe.utils import add_days, today

	if frappe.db.exists("Bin", {"warehouse": store, "item_code": "DOLO-650", "actual_qty": (">", 0)}):
		return
	rows = []
	for code, batches in STORE_STOCK.items():
		row = next(r for r in ITEMS if r[0] == code)
		units, mrp, ptr = row[13], row[17], row[18]
		for suffix, days, qty in batches:
			batch_id = f"{code}-{suffix}"
			if not frappe.db.exists("Batch", batch_id):
				frappe.get_doc({"doctype": "Batch", "batch_id": batch_id, "item": code, "supplier_batch_no": suffix,
					"manufacturing_date": add_days(today(), min(days, 0) - 400), "expiry_date": add_days(today(), days),
					"nir_mrp": mrp, "nir_mrp_uom": row[12]}).insert(ignore_permissions=True)
			rows.append({"item_code": code, "warehouse": store, "qty": qty, "valuation_rate": flt(ptr) / units,
				"batch_no": batch_id, "use_serial_batch_fields": 1})
	opening_account = frappe.db.get_value("Account", {"company": company, "account_name": "Temporary Opening", "is_group": 0})
	reco = frappe.get_doc({"doctype": "Stock Reconciliation", "company": company, "purpose": "Opening Stock",
		"expense_account": opening_account, "items": rows})
	reco.insert(ignore_permissions=True)
	reco.submit()


def recall_hold(company, batch):
	if not frappe.db.exists("Stock Hold", {"batch_no": batch, "status": "Active"}):
		frappe.get_doc({"doctype": "Stock Hold", "company": company, "hold_type": "Recall",
			"item_code": frappe.db.get_value("Batch", batch, "item"), "batch_no": batch,
			"reference": "CDSCO/RECALL/DEMO-01", "reason": "Demo: manufacturer recall of this batch"}).insert(ignore_permissions=True)


def inclusive_tax_template(company, abbr):
	"""Copy of the in-state GST template with tax included in the price, so bills are at MRP."""
	name = f"Output GST In-state (MRP Inclusive) - {abbr}"
	if not frappe.db.exists("Sales Taxes and Charges Template", name):
		source = frappe.get_doc("Sales Taxes and Charges Template", f"Output GST In-state - {abbr}")
		copy = frappe.copy_doc(source)
		copy.title = "Output GST In-state (MRP Inclusive)"
		# India Compliance allows one template per tax category; this one is chosen on the POS Profile instead
		copy.tax_category = None
		copy.is_default = 0
		for row in copy.taxes:
			row.included_in_print_rate = 1
		copy.insert(ignore_permissions=True)
		name = copy.name
	return name


def sample_bills(company, profile, store, walk_in, taxes):
	"""A few submitted bills: loose sale, senior-citizen discount, Rx item with prescription."""
	from frappe.utils import today

	# POS Settings decides whether the POS screen makes POS Invoices or Sales Invoices; follow it
	doctype = frappe.db.get_single_value("POS Settings", "invoice_type") or "POS Invoice"
	if frappe.db.exists(doctype, {"pos_profile": profile, "docstatus": 1}):
		return []
	bills = [
		(walk_in, [("DOLO-650", 1, "Strip"), ("DOLO-650", 5, "Tablet"), ("CALPOL-500", 2, "Strip")], {}),
		("Mr. R. Iyer", [("PAN-40", 1, "Strip"), ("GLYCOMET-500", 2, "Strip"), ("NIR-PCM-500", 1, "Strip")],
			{"nir_prescription": "/files/demo-prescription.pdf", "nir_doctor_name": "Dr. M. Nair", "nir_doctor_reg_no": "MMC-24680"}),
		(walk_in, [("ALPRAX-025", 1, "Strip"), ("VOLINI-30", 1, "Tube")],
			{"nir_prescription": "/files/demo-prescription.pdf", "nir_doctor_name": "Dr. S. Rao", "nir_doctor_reg_no": "MMC-67890"}),
	]
	created = []
	for customer, lines, extra in bills:
		invoice = frappe.get_doc({"doctype": doctype, "company": company, "pos_profile": profile, "customer": customer,
			"posting_date": today(), "is_pos": 1, "is_created_using_pos": 1, "update_stock": 1, "set_warehouse": store,
			"taxes_and_charges": taxes,
			"items": [{"item_code": code, "qty": qty, "uom": uom, "warehouse": store} for code, qty, uom in lines],
			"payments": [{"mode_of_payment": "Cash", "amount": 0, "default": 1}], **extra})
		invoice.set_missing_values()
		invoice.insert(ignore_permissions=True)
		invoice.payments[0].amount = invoice.rounded_total or invoice.grand_total
		invoice.save(ignore_permissions=True)
		invoice.submit()
		created.append(invoice.name)
	return created


ONLINE_PINCODES = {
	# store: [(pincode, delivery type, km, hours)]
	"Store Andheri": [("400053", "Express 2hr", 1.5, 2), ("400058", "Same Day", 3.0, 6), ("400049", "Same Day", 5.5, 6)],
	"Store Bandra": [("400050", "Express 2hr", 1.0, 2), ("400052", "Same Day", 3.5, 6), ("400049", "Same Day", 6.0, 6)],
}


ONLINE_TEST_GSTIN = "27AAPFU0939F1ZV"


def create_online_order_data(company="_Test Pharmacy"):
	"""Online ordering: settings, store pincodes and addresses, delivery charge account, a coupon and a loyalty programme.

	Run: bench --site pharmacy.local execute pharmacy.demo_data.create_online_order_data
	Online payment also needs Razorpay Settings (test keys) and a Payment Gateway Account; COD works without them.
	"""
	abbr = frappe.db.get_value("Company", company, "abbr")
	income = f"Delivery Charges - {abbr}"
	ensure("Account", income, {"account_name": "Delivery Charges", "company": company,
		"parent_account": f"Indirect Income - {abbr}", "account_type": "Income Account", "root_type": "Income"})

	for store, pins in ONLINE_PINCODES.items():
		doc = frappe.get_doc("Pharmacy Store", store)
		doc.online_orders = 1
		# GST-valid test GSTIN for the store's billing address (both stores are in Maharashtra under one registration)
		doc.address = doc.address or store_address(company, store, ONLINE_TEST_GSTIN, pins[0][0])
		existing = {p.pincode for p in doc.pincodes_served}
		for pincode, delivery_type, km, hours in pins:
			if pincode not in existing:
				doc.append("pincodes_served", {"pincode": pincode, "delivery_type": delivery_type, "is_active": 1,
					"distance_km": km, "delivery_hours": hours, "cod_allowed": 1})
		doc.flags.ignore_permissions = True
		doc.save()
		doc.db_set({"nir_approval_status": "Approved", "disabled": 0}) if doc.meta.has_field("nir_approval_status") else None

	settings = frappe.get_doc("Online Order Settings")
	settings.update({
		"company": company, "price_list": "Standard Selling", "taxes_and_charges": f"Output GST In-state (MRP Inclusive) - {abbr}",
		"customer_group": "Individual", "territory": frappe.db.get_value("Territory", {"is_group": 0, "name": ("like", "%Maharashtra%")}) or "India",
		"min_order_value": 100, "fulfilment_mode": "Split", "dc_warehouse": f"Main DC - {abbr}", "dc_ships_to_all_pincodes": 1,
		"dc_delivery_hours": 48, "store_order_cutoff": "18:00:00", "delivery_charge": 40, "free_delivery_above": 500,
		"delivery_charge_account": income, "cod_enabled": 1, "cod_max_amount": 5000, "cod_mode_of_payment": "Cash",
		"prescription_validity_days": 180, "payment_success_path": "/orders",
	})
	settings.payment_gateway_account = frappe.db.get_value("Payment Gateway Account", {"payment_gateway": "Razorpay", "currency": "INR"})
	settings.flags.ignore_permissions = True
	settings.save()

	online_coupon(company)
	loyalty_programme(company, abbr)
	frappe.db.commit()
	return "Online ordering ready: pincodes 400053/400058 (Andheri), 400050/400052 (Bandra), 400049 (both); coupon WELCOME10"


def store_address(company, store, gstin, pincode):
	name = frappe.db.get_value("Address", {"address_title": store, "is_your_company_address": 1})
	if name:
		return name
	address = frappe.get_doc({
		"doctype": "Address", "address_title": store, "address_type": "Billing", "address_line1": f"{store}, Shop 4, Main Road",
		"city": "Mumbai", "state": "Maharashtra", "pincode": pincode, "country": "India", "gstin": gstin,
		"gst_category": "Registered Regular", "is_your_company_address": 1, "links": [{"link_doctype": "Company", "link_name": company}],
	})
	address.insert(ignore_permissions=True)
	return address.name


def online_coupon(company):
	rule = frappe.db.get_value("Pricing Rule", {"title": "Online Welcome 10%"})
	rule = rule or frappe.get_doc({"doctype": "Pricing Rule", **{
		"title": "Online Welcome 10%", "apply_on": "Item Group", "selling": 1, "company": company, "coupon_code_based": 1,
		"rate_or_discount": "Discount Percentage", "discount_percentage": 10, "priority": 5,
		"item_groups": [{"item_group": "All Item Groups"}], "valid_from": frappe.utils.nowdate(),
	}}).insert(ignore_permissions=True).name
	if not frappe.db.exists("Coupon Code", {"coupon_code": "WELCOME10"}):
		frappe.get_doc({"doctype": "Coupon Code", "coupon_name": "Online Welcome", "coupon_type": "Promotional",
			"coupon_code": "WELCOME10", "pricing_rule": rule, "maximum_use": 1000}).insert(ignore_permissions=True)


def loyalty_programme(company, abbr):
	if frappe.db.exists("Loyalty Program", "Pharmacy Rewards"):
		return
	frappe.get_doc({
		"doctype": "Loyalty Program", "loyalty_program_name": "Pharmacy Rewards", "loyalty_program_type": "Single Tier Program",
		"company": company, "from_date": frappe.utils.nowdate(), "conversion_factor": 0.25, "expiry_duration": 365,
		"auto_opt_in": 1, "customer_group": "Individual", "customer_territory": frappe.db.get_value("Territory", {"is_group": 1, "parent_territory": ""}) or "All Territories",
		"expense_account": frappe.db.get_value("Account", {"company": company, "account_name": ("like", "%Marketing%")}) or f"Miscellaneous Expenses - {abbr}",
		"cost_center": frappe.get_cached_value("Company", company, "cost_center"),
		"collection_rules": [{"tier_name": "Member", "collection_factor": 100, "min_spent": 0}],
	}).insert(ignore_permissions=True)
