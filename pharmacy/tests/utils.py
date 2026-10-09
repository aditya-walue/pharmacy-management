import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.utils import getdate

from pharmacy.install import setup


def before_tests():
	"""Complete the setup wizard with an Indian test company, as ERPNext's own hook only runs for erpnext tests."""
	frappe.clear_cache()
	setup()

	today = getdate()
	fy_start_year = today.year if today.month >= 4 else today.year - 1
	fy_name = f"{fy_start_year}-{fy_start_year + 1}"

	if not frappe.db.a_row_exists("Company"):
		setup_complete(
			{
				"currency": "INR",
				"full_name": "Test User",
				"company_name": "_Test Pharmacy",
				"company_abbr": "_TP",
				"timezone": "Asia/Kolkata",
				"country": "India",
				"fy_start_date": f"{fy_start_year}-04-01",
				"fy_end_date": f"{fy_start_year + 1}-03-31",
				"language": "english",
				"chart_of_accounts": "Standard",
			}
		)

	if frappe.db.exists("Fiscal Year", fy_name):
		fy_doc = frappe.get_doc("Fiscal Year", fy_name)
	else:
		fy_doc = frappe.get_doc({
			"doctype": "Fiscal Year",
			"year": fy_name,
			"year_start_date": f"{fy_start_year}-04-01",
			"year_end_date": f"{fy_start_year + 1}-03-31",
			"companies": [],
		})

	existing_companies = {c.company for c in fy_doc.companies}
	for comp in frappe.get_all("Company", pluck="name"):
		if comp not in existing_companies:
			fy_doc.append("companies", {"company": comp})

	if frappe.db.exists("Company", "_Test Company"):
		if not frappe.db.exists("Warehouse", "_Test Warehouse Group - _TC"):
			frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": "_Test Warehouse Group",
				"is_group": 1,
				"company": "_Test Company",
			}).insert(ignore_if_duplicate=True)

		if not frappe.db.exists("Warehouse", "_Test Warehouse Group-C1 - _TC"):
			frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": "_Test Warehouse Group-C1",
				"parent_warehouse": "_Test Warehouse Group - _TC",
				"is_group": 0,
				"company": "_Test Company",
			}).insert(ignore_if_duplicate=True)

	frappe.db.sql("UPDATE `tabItem` SET disabled=0, nir_approval_status='Approved' WHERE disabled=1")
	frappe.db.sql("UPDATE `tabSupplier` SET disabled=0, nir_approval_status='Approved' WHERE disabled=1")
	frappe.db.sql("UPDATE `tabCustomer` SET disabled=0, nir_approval_status='Approved' WHERE disabled=1")

	if frappe.db.exists("Supplier", "_Test Supplier"):
		if not frappe.db.exists("Drug Licence", {"party_type": "Supplier", "party": "_Test Supplier"}):
			frappe.get_doc({
				"doctype": "Drug Licence",
				"party_type": "Supplier",
				"party": "_Test Supplier",
				"licence_no": "LIC-SUP-TEST-001",
				"licence_form": "20B",
				"scope": "Wholesale",
				"valid_from": "2000-01-01",
				"valid_upto": "2035-12-31",
				"status": "Active",
			}).insert(ignore_permissions=True)

	for wh in frappe.get_all("Warehouse", filters={"is_group": 0}, pluck="name"):
		if "unlicensed" in wh.lower():
			continue
		if not frappe.db.exists("Drug Licence", {"party_type": "Warehouse", "party": wh, "licence_form": "20B"}):
			frappe.get_doc({
				"doctype": "Drug Licence",
				"party_type": "Warehouse",
				"party": wh,
				"licence_no": f"LIC-WH-WS-{wh[:10]}",
				"licence_form": "20B",
				"scope": "Wholesale",
				"valid_from": "2000-01-01",
				"valid_upto": "2035-12-31",
				"status": "Active",
			}).insert(ignore_permissions=True, ignore_if_duplicate=True)
		if not frappe.db.exists("Drug Licence", {"party_type": "Warehouse", "party": wh, "licence_form": "20"}):
			frappe.get_doc({
				"doctype": "Drug Licence",
				"party_type": "Warehouse",
				"party": wh,
				"licence_no": f"LIC-WH-RET-{wh[:10]}",
				"licence_form": "20",
				"scope": "Retail",
				"valid_from": "2000-01-01",
				"valid_upto": "2035-12-31",
				"status": "Active",
			}).insert(ignore_permissions=True, ignore_if_duplicate=True)

	# Delete any licences on root/group warehouses or unlicensed stores
	group_whs = frappe.get_all("Warehouse", filters={"is_group": 1}, pluck="name")
	if group_whs:
		frappe.db.delete("Drug Licence", {"party_type": "Warehouse", "party": ("in", group_whs)})
	frappe.db.sql("DELETE FROM `tabDrug Licence` WHERE party LIKE '%unlicensed%' OR party LIKE '%Unlicensed%'")
	frappe.db.delete("Item Price", {"item_code": ("like", "_Test Item%")})

	fy_doc.save(ignore_permissions=True)
	frappe.db.commit()


def make_test_item(item_code, **kwargs):
	if not frappe.db.exists("Item", item_code):
		defaults = {
			"doctype": "Item",
			"item_code": item_code,
			"item_group": frappe.db.get_value(
				"Item Group", {"is_group": 1, "parent_item_group": ("is", "not set")}
			),
			"stock_uom": "Nos",
			"gst_hsn_code": "30049099",
			"is_stock_item": 1,
			"nir_regulatory_category": "Schedule H",
			"nir_storage_condition": "Ambient",
			"nir_approval_status": "Approved",
			"disabled": 0,
		}
		defaults.update(kwargs)
		return frappe.get_doc(defaults).insert()
	return frappe.get_doc("Item", item_code)
