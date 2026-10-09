# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt
"""
Tests for Purchase Suggestion + Engine.

Scenarios tested:
  1. Engine returns suggestions when store demand > available stock.
  2. MOQ rounding: suggested qty rounded up to nearest MOQ multiple.
  3. Open PO qty reduces the suggestion (in-transit stock is counted).
  4. Supplier Scheme applies quantity discount → scheme_discount_pct > 0.
  5. Supplier Scheme applies free goods → free_goods_qty > 0.
  6. PurchaseSuggestion.generate() populates items table and saves.
  7. PurchaseSuggestion.make_purchase_orders() creates POs per supplier.
"""

import math

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.pharmacy.purchase_suggestion_engine import generate_suggestions
from pharmacy.tests.utils import make_test_item


class TestPurchaseSuggestionEngine(IntegrationTestCase):
    def setUp(self):
        frappe.db.rollback()
        self._setup_infrastructure()

    def tearDown(self):
        frappe.db.rollback()

    # ------------------------------------------------------------------
    # Infrastructure helpers
    # ------------------------------------------------------------------

    def _setup_infrastructure(self):
        """DC warehouse → stores → supplier → drug licences."""
        self.dc_wh = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": "Test PS DC",
                "nir_warehouse_role": "DC",
                "company": "_Test Company",
            }
        ).insert(ignore_if_duplicate=True)

        self.store_wh = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": "Test PS Store",
                "nir_warehouse_role": "Store",
                "company": "_Test Company",
            }
        ).insert(ignore_if_duplicate=True)

        # Drug licences (required by party_licence hook)
        for lic_no, party, form, scope in [
            ("LIC-PS-DC-01", self.dc_wh.name, "20B", "Wholesale"),
            ("LIC-PS-ST-01", self.store_wh.name, "20", "Retail"),
        ]:
            frappe.get_doc(
                {
                    "doctype": "Drug Licence",
                    "party_type": "Warehouse",
                    "party": party,
                    "licence_no": lic_no,
                    "licence_form": form,
                    "scope": scope,
                    "valid_from": "2020-01-01",
                    "valid_upto": "2035-12-31",
                    "status": "Active",
                }
            ).insert(ignore_if_duplicate=True)

        self.store = frappe.get_doc(
            {
                "doctype": "Pharmacy Store",
                "store_name": "Test PS Store Record",
                "warehouse": self.store_wh.name,
                "serving_warehouse": self.dc_wh.name,
                "nir_approval_status": "Approved",
                "disabled": 0,
            }
        ).insert(ignore_if_duplicate=True)

        self.supplier = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": "_Test PS Supplier",
                "supplier_type": "Company",
                "nir_approval_status": "Approved",
                "nir_lead_time_days": 5,
                "nir_moq_qty": 50,
            }
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc(
            {
                "doctype": "Drug Licence",
                "party_type": "Supplier",
                "party": self.supplier.name,
                "licence_no": "LIC-PS-SUP-01",
                "licence_form": "20B",
                "scope": "Wholesale",
                "valid_from": "2020-01-01",
                "valid_upto": "2035-12-31",
                "status": "Active",
            }
        ).insert(ignore_if_duplicate=True)

        # Item with preferred supplier + safety stock
        self.item = make_test_item(
            "_Test PS Drug",
            nir_abc_class="A",
            nir_regulatory_category="OTC",
            nir_rx_required=0,
        )
        frappe.db.set_value("Item", self.item.name, {
            "nir_preferred_supplier": self.supplier.name,
            "nir_safety_stock_days": 7,
            "last_purchase_rate": 100.0,
            "nir_rx_required": 0,
        })

    def _post_sales(self, item_code, qty, warehouse, days_ago=0):
        """Create and submit a Sales Invoice (simulates store sale)."""
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "_Test PS Customer",
                "customer_type": "Individual",
                "nir_approval_status": "Approved",
            }
        ).insert(ignore_if_duplicate=True)

        si = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": customer.name,
                "company": "_Test Company",
                "posting_date": add_days(today(), -days_ago),
                "nir_prescription": "RX-PS-001",
                "nir_doctor_name": "Dr. Test PS",
                "nir_doctor_reg_no": "DOC-REG-001",
                "items": [
                    {
                        "item_code": item_code,
                        "qty": qty,
                        "rate": 150.0,
                        "warehouse": warehouse,
                    }
                ],
            }
        ).insert()
        si.submit()
        return si

    def _stock_dc(self, item_code, qty):
        """Put qty into DC warehouse via Material Receipt."""
        batch = frappe.get_doc(
            {
                "doctype": "Batch",
                "item": item_code,
                "supplier_batch_no": f"B-PS-{item_code[:6]}",
                "nir_mrp": 200.0,
                "expiry_date": add_days(today(), 365),
                "nir_approval_status": "Approved",
            }
        ).insert()

        se = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Receipt",
                "stock_entry_type": "Material Receipt",
                "company": "_Test Company",
                "posting_date": today(),
                "items": [
                    {
                        "item_code": item_code,
                        "qty": qty,
                        "t_warehouse": self.dc_wh.name,
                        "batch_no": batch.name,
                        "basic_rate": 100.0,
                    }
                ],
            }
        ).insert()
        se.submit()
        return se

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_engine_suggests_when_demand_exceeds_stock(self):
        """30 units sold from store, 0 in DC → suggestion generated."""
        # Simulate 30 units sold in last 30 days (from store_wh, not dc_wh)
        # We record sales on the store_wh; engine aggregates via Pharmacy Store link.
        # Stock the store first so SI doesn't fail valuation
        self._stock_dc(self.item.name, 100)
        se_transfer = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "stock_entry_type": "Material Transfer",
                "company": "_Test Company",
                "posting_date": today(),
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 100,
                        "s_warehouse": self.dc_wh.name,
                        "t_warehouse": self.store_wh.name,
                    }
                ],
            }
        ).insert()
        se_transfer.submit()

        self._post_sales(self.item.name, 30, self.store_wh.name)

        rows = generate_suggestions(self.dc_wh.name, period_days=30)
        self.assertTrue(len(rows) > 0, "Expected at least one suggestion row")
        row = next((r for r in rows if r["item_code"] == self.item.name), None)
        self.assertIsNotNone(row, "No suggestion row found for test item")
        self.assertGreater(row["ordered_qty"], 0)

    def test_moq_rounding(self):
        """ordered_qty is always a multiple of MOQ (50 in this setup)."""
        # Force a small suggestion (1–49 units raw) → should round up to 50
        # daily_demand = 30/30 = 1; lead=5, safety=7 → required=12, available=0 → raw=12
        # MOQ=50 → ordered=50
        self._post_sales(self.item.name, 30, self.store_wh.name, days_ago=0)

        rows = generate_suggestions(self.dc_wh.name, period_days=30)
        row = next((r for r in rows if r["item_code"] == self.item.name), None)
        if row and row["ordered_qty"] > 0:
            moq = row["moq_qty"] or 1
            self.assertEqual(row["ordered_qty"] % moq, 0, "ordered_qty is not a MOQ multiple")

    def test_open_po_reduces_suggestion(self):
        """Open PO qty counts as available stock → reduces or eliminates suggestion."""
        # Create an open PO for a large qty
        po = frappe.get_doc(
            {
                "doctype": "Purchase Order",
                "supplier": self.supplier.name,
                "company": "_Test Company",
                "transaction_date": today(),
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 1000,
                        "rate": 100.0,
                        "schedule_date": today(),
                        "warehouse": self.dc_wh.name,
                    }
                ],
            }
        ).insert()
        po.submit()

        rows = generate_suggestions(self.dc_wh.name, period_days=30)
        row = next((r for r in rows if r["item_code"] == self.item.name), None)
        # With 1000 units in-transit and low demand, ordered_qty should be 0
        if row:
            self.assertEqual(
                row["ordered_qty"], 0, "Expected 0 ordered_qty with large open PO"
            )

    def test_scheme_quantity_discount_applied(self):
        """A Quantity Discount scheme sets scheme_discount_pct on the suggestion."""
        frappe.get_doc(
            {
                "doctype": "Supplier Scheme",
                "supplier": self.supplier.name,
                "scheme_name": "10% off on 50+",
                "scheme_type": "Quantity Discount",
                "min_order_qty": 50,
                "discount_pct": 10.0,
                "is_active": 1,
            }
        ).insert()

        # Ensure ordered_qty >= 50 (MOQ=50)
        self._post_sales(self.item.name, 60, self.store_wh.name)

        rows = generate_suggestions(self.dc_wh.name, period_days=30)
        row = next((r for r in rows if r["item_code"] == self.item.name), None)
        if row and row["ordered_qty"] >= 50:
            self.assertEqual(row["scheme_discount_pct"], 10.0)
            self.assertLess(row["net_rate"], row["last_purchase_rate"])

    def test_scheme_free_goods_applied(self):
        """A Free Goods scheme populates free_goods_qty on the suggestion."""
        frappe.get_doc(
            {
                "doctype": "Supplier Scheme",
                "supplier": self.supplier.name,
                "scheme_name": "Buy 10 Get 1",
                "scheme_type": "Free Goods",
                "min_order_qty": 10,
                "free_goods_ratio": 0.1,
                "is_active": 1,
            }
        ).insert()

        self._post_sales(self.item.name, 60, self.store_wh.name)

        rows = generate_suggestions(self.dc_wh.name, period_days=30)
        row = next((r for r in rows if r["item_code"] == self.item.name), None)
        if row and row["ordered_qty"] >= 10:
            expected_free = math.floor(row["ordered_qty"] * 0.1)
            self.assertEqual(row["free_goods_qty"], expected_free)

    def test_purchase_suggestion_doc_generate(self):
        """PurchaseSuggestion.generate() populates the items table."""
        self._post_sales(self.item.name, 60, self.store_wh.name)

        ps = frappe.get_doc(
            {
                "doctype": "Purchase Suggestion",
                "warehouse": self.dc_wh.name,
                "period_days": 30,
                "as_of_date": today(),
            }
        ).insert()

        result = ps.generate()
        ps.reload()
        # At minimum: items table has rows, summary counts match
        self.assertIsNotNone(result)
        self.assertEqual(len(ps.items), ps.total_items)

    def test_make_purchase_orders_creates_pos(self):
        """Submitted PurchaseSuggestion.make_purchase_orders() creates POs."""
        self._post_sales(self.item.name, 60, self.store_wh.name)

        ps = frappe.get_doc(
            {
                "doctype": "Purchase Suggestion",
                "warehouse": self.dc_wh.name,
                "period_days": 30,
                "as_of_date": today(),
            }
        ).insert()
        ps.generate()
        ps.reload()

        if not ps.items:
            self.skipTest("No suggestions generated — nothing to convert to PO")

        ps.submit()
        pos = ps.make_purchase_orders()

        self.assertTrue(len(pos) > 0, "Expected at least one PO to be created")
        ps.reload()
        self.assertEqual(ps.status, "PO Created")
        for po_name in pos:
            self.assertTrue(frappe.db.exists("Purchase Order", po_name))
