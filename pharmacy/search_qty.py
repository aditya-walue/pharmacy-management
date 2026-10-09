import frappe

def search_0067():
    print("=== SEARCHING FOR 0.067 ===")
    for doctype in ["Sales Order Item", "Delivery Note Item", "Sales Invoice Item", "Stock Ledger Entry", "Bin", "Item Price", "UOM Conversion Detail"]:
        try:
            records = frappe.db.sql(f"""
                select parent, name, item_code, qty, stock_qty, uom, conversion_factor 
                from `tab{doctype}` 
                where qty between 0.06 and 0.07 or stock_qty between 0.06 and 0.07
            """, as_dict=True)
            if records:
                print(f"FOUND IN {doctype}:", records)
            else:
                # check if field names differ
                pass
        except Exception as e:
            # check sle or bin
            try:
                sle = frappe.db.sql(f"""
                    select name, voucher_type, voucher_no, item_code, actual_qty, qty_after_transaction 
                    from `tab{doctype}`
                    where abs(actual_qty) between 0.06 and 0.07
                """, as_dict=True)
                if sle:
                    print(f"FOUND IN {doctype} (actual_qty):", sle)
            except Exception:
                pass

if __name__ == "__main__":
    search_0067()
