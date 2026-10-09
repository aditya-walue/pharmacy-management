import frappe

def debug():
    versions = frappe.db.sql("select docname, ref_doctype, creation, data from `tabVersion` where data like '%0.06%'", as_dict=True)
    print("VERSIONS with 0.06:", versions)

    # Search in all child tables for 0.067
    for table in ["tabSales Order Item", "tabDelivery Note Item", "tabSales Invoice Item", "tabPurchase Order Item", "tabPurchase Receipt Item", "tabMaterial Request Item", "tabStock Entry Detail"]:
        res = frappe.db.sql(f"select parent, item_code, qty, uom, conversion_factor, stock_qty from `{table}` where qty between 0.06 and 0.07 or stock_qty between 0.06 and 0.07", as_dict=True)
        if res:
            print(f"FOUND IN {table}:", res)
