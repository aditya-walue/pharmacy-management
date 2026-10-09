"""
Purchase Suggestion Engine
==========================
Generates purchase suggestions for a DC warehouse based on:

  · Combined store demand (Sales Invoice + POS Invoice from stores served by DC)
    + online demand (open Sales Order items fulfilled from the DC)
  · Current stock at the warehouse (Bin actual_qty)
  · Open Purchase Orders — in-transit stock not yet received
  · Lead time  — from Item Supplier table › Supplier.nir_lead_time_days › fallback 7 days
  · Safety stock — safety_stock_days × daily_demand
        safety_stock_days: Item.nir_safety_stock_days › ABC class default (A=7, B=14, C=30)
  · MOQ — Item Supplier.min_order_qty › Supplier.nir_moq_qty; suggested qty rounded up
  · Supplier Schemes — Quantity Discount or Free Goods applied to ordered qty / rate

Usage::

    from pharmacy.pharmacy.purchase_suggestion_engine import generate_suggestions
    rows = generate_suggestions("Main DC - NIR", period_days=30)
"""

import math

import frappe
from frappe.utils import add_days, cint, flt, getdate, today


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_suggestions(warehouse, period_days=30, as_of_date=None):
    """
    Return a list of suggestion dicts for items that need purchasing.

    :param warehouse:    DC warehouse name.
    :param period_days:  Trailing days used to calculate demand.
    :param as_of_date:   Calculation reference date; defaults to today.
    :returns:            List[dict] sorted descending by estimated_value.
                         Only items with ordered_qty > 0 are returned.
    """
    as_of_date = getdate(as_of_date or today())
    from_date = add_days(as_of_date, -period_days)

    items = _get_relevant_items(warehouse, from_date, as_of_date)
    if not items:
        return []

    suggestions = []
    for item_code in items:
        row = _suggest_for_item(item_code, warehouse, period_days, as_of_date, from_date)
        if row and flt(row.get("ordered_qty", 0)) > 0:
            suggestions.append(row)

    suggestions.sort(key=lambda r: r.get("estimated_value", 0), reverse=True)
    return suggestions


# ---------------------------------------------------------------------------
# Item collection
# ---------------------------------------------------------------------------

def _get_relevant_items(warehouse, from_date, as_of_date):
    """Collect item codes to evaluate for this DC."""
    items: set[str] = set()

    # 1. Items currently in stock at the DC
    bins = frappe.get_all(
        "Bin",
        filters={"warehouse": ("in", _dc_warehouses(warehouse)), "actual_qty": (">", 0)},
        pluck="item_code",
    )
    items.update(bins)

    # 2. Items sold from stores served by this DC
    stores = _get_served_store_warehouses(warehouse)
    if stores:
        for table, parent_table, wh_field, date_field in [
            ("Sales Invoice Item", "Sales Invoice", "warehouse", "posting_date"),
            ("POS Invoice Item", "POS Invoice", "warehouse", "posting_date"),
        ]:
            rows = frappe.db.sql(
                f"""
                SELECT DISTINCT i.item_code
                FROM `tab{table}` i
                JOIN `tab{parent_table}` p ON p.name = i.parent
                WHERE p.docstatus = 1
                  AND i.{wh_field} IN %(stores)s
                  AND p.{date_field} BETWEEN %(from_date)s AND %(as_of_date)s
                """,
                {"stores": stores, "from_date": from_date, "as_of_date": as_of_date},
                as_list=True,
            )
            items.update(r[0] for r in rows)

    # 3. Items on open Purchase Orders for this warehouse
    po_items = frappe.db.sql(
        """
        SELECT DISTINCT poi.item_code
        FROM `tabPurchase Order Item` poi
        JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE po.docstatus = 1
          AND po.status NOT IN ('Closed','Cancelled')
          AND poi.warehouse IN %(wh)s
          AND poi.received_qty < poi.qty
        """,
        {"wh": tuple(_dc_warehouses(warehouse))},
        as_list=True,
    )
    items.update(r[0] for r in po_items)

    # 4. Online Sales Order items (pending delivery) from this DC
    online_items = frappe.db.sql(
        """
        SELECT DISTINCT soi.item_code
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
          AND so.status NOT IN ('Closed','Cancelled','Completed')
          AND soi.warehouse IN %(wh)s
          AND so.nir_is_patient_special_order = 0
        """,
        {"wh": tuple(_dc_warehouses(warehouse))},
        as_list=True,
    )
    items.update(r[0] for r in online_items)

    return list(items)


def _dc_warehouses(dc_warehouse):
    """The DC and every zone / bin under it: stock, open POs and online orders sit in the bins."""
    lft, rgt = frappe.db.get_value("Warehouse", dc_warehouse, ["lft", "rgt"])
    return frappe.get_all("Warehouse", filters={"lft": (">=", lft), "rgt": ("<=", rgt)}, pluck="name") or [dc_warehouse]


def _get_served_store_warehouses(dc_warehouse):
    return frappe.get_all(
        "Pharmacy Store",
        filters={"serving_warehouse": dc_warehouse, "disabled": 0},
        pluck="warehouse",
    ) or []


# ---------------------------------------------------------------------------
# Per-item calculation
# ---------------------------------------------------------------------------

def _suggest_for_item(item_code, warehouse, period_days, as_of_date, from_date):
    """Calculate a single suggestion row dict."""
    try:
        item = frappe.get_cached_doc("Item", item_code)
    except Exception:
        return None

    # ── Stock ──────────────────────────────────────────────────────────────
    current_stock = flt(
        frappe.db.sql(
            "SELECT COALESCE(SUM(actual_qty), 0) FROM `tabBin` WHERE item_code = %s AND warehouse IN %s",
            (item_code, tuple(_dc_warehouses(warehouse))),
        )[0][0]
    )
    open_po_qty = _open_po_qty(item_code, warehouse)

    # ── Demand ─────────────────────────────────────────────────────────────
    store_demand = _store_demand(item_code, warehouse, from_date, as_of_date)
    online_demand = _online_demand(item_code, warehouse, from_date, as_of_date)
    total_demand = store_demand + online_demand

    if total_demand == 0 and current_stock == 0 and open_po_qty == 0:
        return None

    daily_demand = total_demand / period_days if period_days > 0 else 0.0

    # ── Supplier info ───────────────────────────────────────────────────────
    preferred_supplier, lead_time_days, moq_qty, last_purchase_rate = _supplier_info(
        item_code, warehouse
    )

    # ── Safety stock ───────────────────────────────────────────────────────
    safety_stock_days = cint(item.get("nir_safety_stock_days") or 0) or _abc_safety_days(item)
    safety_stock_qty = daily_demand * safety_stock_days

    # ── Required vs available ───────────────────────────────────────────────
    demand_during_lead_time = daily_demand * lead_time_days
    required_qty = demand_during_lead_time + safety_stock_qty
    available_qty = current_stock + open_po_qty

    raw_suggested = max(0.0, required_qty - available_qty)

    # ── MOQ rounding ────────────────────────────────────────────────────────
    if raw_suggested > 0 and moq_qty > 0:
        ordered_qty = math.ceil(raw_suggested / moq_qty) * moq_qty
    else:
        ordered_qty = raw_suggested

    # ── Scheme ──────────────────────────────────────────────────────────────
    scheme_name, scheme_discount_pct, free_goods_qty = _best_scheme(
        item_code, preferred_supplier, ordered_qty, last_purchase_rate
    )

    net_rate = flt(last_purchase_rate * (1 - scheme_discount_pct / 100))
    estimated_value = flt(ordered_qty * net_rate)

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        # every quantity and rate here is per stock unit, so the line must be too
        "uom": item.stock_uom,
        "abc_class": item.get("nir_abc_class") or "",
        # stock
        "current_stock": current_stock,
        "open_po_qty": open_po_qty,
        # demand
        "store_demand_qty": store_demand,
        "online_demand_qty": online_demand,
        "total_demand_qty": total_demand,
        "daily_demand": round(daily_demand, 4),
        # lead / safety
        "lead_time_days": lead_time_days,
        "safety_stock_days": safety_stock_days,
        "safety_stock_qty": round(safety_stock_qty, 2),
        "required_qty": round(required_qty, 2),
        "available_qty": round(available_qty, 2),
        # order
        "suggested_qty": round(raw_suggested, 2),
        "moq_qty": moq_qty,
        "ordered_qty": ordered_qty,
        # supplier & scheme
        "preferred_supplier": preferred_supplier,
        "last_purchase_rate": last_purchase_rate,
        "scheme_name": scheme_name,
        "scheme_discount_pct": scheme_discount_pct,
        "free_goods_qty": free_goods_qty,
        "net_rate": net_rate,
        "estimated_value": estimated_value,
        "notes": (f"+{int(free_goods_qty)} units free" if free_goods_qty else ""),
    }


# ---------------------------------------------------------------------------
# Stock helpers
# ---------------------------------------------------------------------------

def _open_po_qty(item_code, warehouse):
    """Qty pending receipt on submitted, open Purchase Orders."""
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM((poi.qty - poi.received_qty) * poi.conversion_factor), 0)
        FROM `tabPurchase Order Item` poi
        JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE po.docstatus = 1
          AND po.status NOT IN ('Closed','Cancelled')
          AND poi.item_code = %(item)s
          AND poi.warehouse IN %(wh)s
          AND poi.received_qty < poi.qty
        """,
        {"item": item_code, "wh": tuple(_dc_warehouses(warehouse))},
    )
    return flt(result[0][0]) if result else 0.0


# ---------------------------------------------------------------------------
# Demand helpers
# ---------------------------------------------------------------------------

def _store_demand(item_code, warehouse, from_date, as_of_date):
    """Total units sold from all stores served by this DC over the period."""
    stores = _get_served_store_warehouses(warehouse)
    if not stores:
        return 0.0

    def _qty(table, parent):
        r = frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(i.stock_qty), 0)
            FROM `tab{table}` i
            JOIN `tab{parent}` p ON p.name = i.parent
            WHERE p.docstatus = 1
              AND i.item_code = %(item)s
              AND i.warehouse IN %(stores)s
              AND p.posting_date BETWEEN %(from_date)s AND %(as_of_date)s
            """,
            {"item": item_code, "stores": stores, "from_date": from_date, "as_of_date": as_of_date},
        )
        return flt(r[0][0]) if r else 0.0

    return _qty("Sales Invoice Item", "Sales Invoice") + _qty("POS Invoice Item", "POS Invoice")


def _online_demand(item_code, warehouse, from_date, as_of_date):
    """
    Unfulfilled online Sales Order qty to be dispatched from this DC.
    Excludes Patient Special Orders (fulfilled from store stock separately).
    """
    r = frappe.db.sql(
        """
        SELECT COALESCE(SUM((soi.qty - soi.delivered_qty) * soi.conversion_factor), 0)
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
          AND so.status NOT IN ('Closed','Cancelled','Completed')
          AND soi.item_code = %(item)s
          AND soi.warehouse IN %(wh)s
          AND so.nir_is_patient_special_order = 0
          AND so.transaction_date BETWEEN %(from_date)s AND %(as_of_date)s
        """,
        {"item": item_code, "wh": tuple(_dc_warehouses(warehouse)), "from_date": from_date, "as_of_date": as_of_date},
    )
    return flt(r[0][0]) if r else 0.0


# ---------------------------------------------------------------------------
# Supplier info helper
# ---------------------------------------------------------------------------

def _supplier_info(item_code, warehouse):
    """
    Return (preferred_supplier, lead_time_days, moq_qty, last_purchase_rate).

    Priority:
      1. Item Supplier table (first supplier by idx)
      2. Item.nir_preferred_supplier custom field
      3. Supplier.nir_lead_time_days / nir_moq_qty
    """
    company = frappe.db.get_value("Warehouse", warehouse, "company")

    # Preferred supplier from Item custom field or Item Supplier child table
    preferred_supplier = (
        frappe.db.get_value("Item", item_code, "nir_preferred_supplier")
        or frappe.db.get_value("Item Supplier", {"parent": item_code}, "supplier", order_by="idx asc")
    )

    item_vals = frappe.db.get_value(
        "Item", item_code, ["lead_time_days", "min_order_qty", "last_purchase_rate"], as_dict=True
    ) or {}

    lead_time_days = cint(item_vals.get("lead_time_days")) or 0
    moq_qty = flt(item_vals.get("min_order_qty")) or 0.0

    if preferred_supplier:
        sup_vals = frappe.db.get_value(
            "Supplier", preferred_supplier, ["nir_lead_time_days", "nir_moq_qty"], as_dict=True
        ) or {}
        if sup_vals.get("nir_lead_time_days"):
            lead_time_days = cint(sup_vals["nir_lead_time_days"])
        if sup_vals.get("nir_moq_qty"):
            moq_qty = flt(sup_vals["nir_moq_qty"])

    if not lead_time_days:
        lead_time_days = 7

    # Last purchase rate from PO history
    last_purchase_rate = 0.0
    if preferred_supplier:
        lr = frappe.db.sql(
            """
            SELECT poi.rate
            FROM `tabPurchase Order Item` poi
            JOIN `tabPurchase Order` po ON po.name = poi.parent
            WHERE po.docstatus = 1
              AND po.supplier = %(sup)s
              AND poi.item_code = %(item)s
              AND po.company = %(co)s
            ORDER BY po.transaction_date DESC
            LIMIT 1
            """,
            {"sup": preferred_supplier, "item": item_code, "co": company},
        )
        if lr:
            last_purchase_rate = flt(lr[0][0])

    if not last_purchase_rate:
        last_purchase_rate = flt(frappe.db.get_value("Item", item_code, "last_purchase_rate") or 0)

    return preferred_supplier, lead_time_days, moq_qty, last_purchase_rate


# ---------------------------------------------------------------------------
# Scheme helper
# ---------------------------------------------------------------------------

def _best_scheme(item_code, supplier, ordered_qty, rate):
    """
    Find the best applicable Supplier Scheme.

    Returns (scheme_name, discount_pct, free_goods_qty).
    """
    if not supplier:
        return "", 0.0, 0.0

    today_str = today()
    schemes = frappe.db.sql(
        """
        SELECT name, scheme_type, min_order_qty, min_order_value,
               discount_pct, free_goods_ratio
        FROM `tabSupplier Scheme`
        WHERE supplier = %(sup)s
          AND is_active = 1
          AND (item_code = %(item)s OR item_code IS NULL OR item_code = '')
          AND (valid_from  IS NULL OR valid_from  = '' OR valid_from  <= %(today)s)
          AND (valid_upto  IS NULL OR valid_upto  = '' OR valid_upto  >= %(today)s)
        ORDER BY min_order_qty DESC, discount_pct DESC
        """,
        {"sup": supplier, "item": item_code, "today": today_str},
        as_dict=True,
    )

    best_scheme = ""
    best_discount = 0.0
    best_free = 0.0

    for s in schemes:
        qty_ok = (flt(s.min_order_qty) <= ordered_qty) if s.min_order_qty else True
        val_ok = (flt(s.min_order_value) <= (ordered_qty * rate)) if s.min_order_value else True
        if not (qty_ok and val_ok):
            continue

        if s.scheme_type in ("Quantity Discount", "Cash Discount"):
            if flt(s.discount_pct) > best_discount:
                best_discount = flt(s.discount_pct)
                best_scheme = s.name
        elif s.scheme_type == "Free Goods":
            fg = math.floor(ordered_qty * flt(s.free_goods_ratio))
            if fg > best_free:
                best_free = fg
                best_scheme = s.name

    return best_scheme, best_discount, best_free


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _abc_safety_days(item_doc):
    """Default safety stock days based on ABC class."""
    return {"A": 7, "B": 14, "C": 30}.get(item_doc.get("nir_abc_class") or "B", 14)
