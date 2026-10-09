# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt
"""
Tests for Patient Special Order on Sales Order.

Patient special orders are tracked as a Sales Order with:
  nir_is_patient_special_order = 1
  nir_patient_name, nir_patient_phone, nir_store, nir_priority
  nir_pso_status  (updated by hooks in overrides.patient_order)

Linked documents (PO, PR, SE, SI) carry nir_patient_sales_order back to
the originating Sales Order so nir_pso_status is kept current.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from pharmacy.tests.utils import make_test_item


class TestPatientSpecialOrderOnSO(IntegrationTestCase):
    def setUp(self):
        frappe.db.rollback()

        self.dc_wh = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": "Test PSO DC Warehouse",
                "nir_warehouse_role": "DC",
                "company": "_Test Company",
            }
        ).insert(ignore_if_duplicate=True)

        self.store_wh = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": "Test PSO Store Warehouse",
                "nir_warehouse_role": "Store",
                "company": "_Test Company",
            }
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc(
            {
                "doctype": "Drug Licence",
                "party_type": "Warehouse",
                "party": self.dc_wh.name,
                "licence_no": "LIC-PSO-DC-001",
                "licence_form": "20B",
                "scope": "Wholesale",
                "valid_from": "2020-01-01",
                "valid_upto": "2035-12-31",
                "status": "Active",
            }
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc(
            {
                "doctype": "Drug Licence",
                "party_type": "Warehouse",
                "party": self.store_wh.name,
                "licence_no": "LIC-PSO-STORE-001",
                "licence_form": "20",
                "scope": "Retail",
                "valid_from": "2020-01-01",
                "valid_upto": "2035-12-31",
                "status": "Active",
            }
        ).insert(ignore_if_duplicate=True)

        self.store = frappe.get_doc(
            {
                "doctype": "Pharmacy Store",
                "store_name": "Test PSO Store",
                "warehouse": self.store_wh.name,
                "serving_warehouse": self.dc_wh.name,
                "nir_approval_status": "Approved",
                "disabled": 0,
            }
        ).insert(ignore_if_duplicate=True)

        self.item = make_test_item("_Test Patient Special Drug", nir_abc_class="A")

        self.customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "_Test PSO Patient Customer",
                "customer_type": "Individual",
                "nir_approval_status": "Approved",
            }
        ).insert(ignore_if_duplicate=True)

    def tearDown(self):
        frappe.db.rollback()

    # ------------------------------------------------------------------
    # Helper: create a patient Sales Order
    # ------------------------------------------------------------------
    def _make_patient_so(self, submit=False):
        so = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "customer": self.customer.name,
                "company": "_Test Company",
                "transaction_date": today(),
                "delivery_date": add_days(today(), 3),
                "nir_is_patient_special_order": 1,
                "nir_patient_name": "Aditi Sharma",
                "nir_patient_phone": "+919876543210",
                "nir_store": self.store.name,
                "nir_priority": "Urgent",
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 5.0,
                        "delivery_date": add_days(today(), 3),
                        "warehouse": self.store_wh.name,
                    }
                ],
            }
        ).insert()
        if submit:
            so.submit()
        return so

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_patient_so_validation_requires_name_and_store(self):
        """nir_patient_name and nir_store must be present when flag is set."""
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Sales Order",
                    "customer": self.customer.name,
                    "company": "_Test Company",
                    "transaction_date": today(),
                    "delivery_date": add_days(today(), 3),
                    "nir_is_patient_special_order": 1,
                    # patient_name missing
                    "nir_store": self.store.name,
                    "items": [
                        {
                            "item_code": self.item.name,
                            "qty": 1.0,
                            "delivery_date": add_days(today(), 3),
                            "warehouse": self.store_wh.name,
                        }
                    ],
                }
            ).insert()

    def test_patient_so_fields_saved(self):
        """Patient fields survive insert without errors."""
        so = self._make_patient_so()
        self.assertEqual(so.nir_is_patient_special_order, 1)
        self.assertEqual(so.nir_patient_name, "Aditi Sharma")
        self.assertEqual(so.nir_store, self.store.name)
        self.assertEqual(so.nir_priority, "Urgent")

    def test_pso_status_updated_by_purchase_order(self):
        """nir_pso_status → PO Issued when a PO with nir_patient_sales_order is submitted."""
        so = self._make_patient_so(submit=True)

        supplier = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": "_Test PSO Supplier",
                "supplier_type": "Company",
                "nir_approval_status": "Approved",
            }
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc(
            {
                "doctype": "Drug Licence",
                "party_type": "Supplier",
                "party": supplier.name,
                "licence_no": "LIC-PSO-SUP-001",
                "licence_form": "20B",
                "scope": "Wholesale",
                "valid_from": "2020-01-01",
                "valid_upto": "2035-12-31",
                "status": "Active",
            }
        ).insert(ignore_if_duplicate=True)

        po = frappe.get_doc(
            {
                "doctype": "Purchase Order",
                "supplier": supplier.name,
                "company": "_Test Company",
                "transaction_date": today(),
                "nir_is_patient_special_order": 1,
                "nir_patient_sales_order": so.name,
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 5.0,
                        "rate": 200.0,
                        "schedule_date": today(),
                        "warehouse": self.dc_wh.name,
                    }
                ],
            }
        ).insert()
        po.submit()

        so.reload()
        self.assertEqual(so.nir_pso_status, "PO Issued")

    def test_pso_status_updated_by_purchase_receipt(self):
        """nir_pso_status → Received at DC when PR is submitted."""
        so = self._make_patient_so(submit=True)

        supplier = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": "_Test PSO Supplier",
                "supplier_type": "Company",
                "nir_approval_status": "Approved",
            }
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc(
            {
                "doctype": "Drug Licence",
                "party_type": "Supplier",
                "party": supplier.name,
                "licence_no": "LIC-PSO-SUP-001",
                "licence_form": "20B",
                "scope": "Wholesale",
                "valid_from": "2020-01-01",
                "valid_upto": "2035-12-31",
                "status": "Active",
            }
        ).insert(ignore_if_duplicate=True)

        batch = frappe.get_doc(
            {
                "doctype": "Batch",
                "item": self.item.name,
                "supplier_batch_no": "PSO-B2",
                "nir_mrp": 300.0,
                "expiry_date": add_days(today(), 365),
                "nir_approval_status": "Approved",
            }
        ).insert()

        pr = frappe.get_doc(
            {
                "doctype": "Purchase Receipt",
                "supplier": supplier.name,
                "company": "_Test Company",
                "posting_date": today(),
                "nir_is_patient_special_order": 1,
                "nir_patient_sales_order": so.name,
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 5.0,
                        "rate": 200.0,
                        "batch_no": batch.name,
                        "warehouse": self.dc_wh.name,
                    }
                ],
            }
        ).insert()
        pr.submit()

        so.reload()
        self.assertEqual(so.nir_pso_status, "Received at DC")

    def test_pso_status_ready_for_pickup_on_stock_entry(self):
        """nir_pso_status → Ready for Pickup when Material Transfer SE is submitted."""
        so = self._make_patient_so(submit=True)

        batch = frappe.get_doc(
            {
                "doctype": "Batch",
                "item": self.item.name,
                "supplier_batch_no": "PSO-B3",
                "nir_mrp": 300.0,
                "expiry_date": add_days(today(), 365),
                "nir_approval_status": "Approved",
            }
        ).insert()

        # Stock the DC warehouse first
        se_in = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Receipt",
                "stock_entry_type": "Material Receipt",
                "company": "_Test Company",
                "posting_date": today(),
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 10.0,
                        "t_warehouse": self.dc_wh.name,
                        "batch_no": batch.name,
                        "basic_rate": 200.0,
                    }
                ],
            }
        ).insert()
        se_in.submit()

        se = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Transfer",
                "stock_entry_type": "Material Transfer",
                "company": "_Test Company",
                "posting_date": today(),
                "nir_is_patient_special_order": 1,
                "nir_patient_sales_order": so.name,
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 5.0,
                        "s_warehouse": self.dc_wh.name,
                        "t_warehouse": self.store_wh.name,
                        "batch_no": batch.name,
                    }
                ],
            }
        ).insert()
        se.submit()

        so.reload()
        self.assertEqual(so.nir_pso_status, "Ready for Pickup")

    def test_pso_status_completed_on_sales_invoice(self):
        """nir_pso_status → Completed when Sales Invoice is submitted."""
        so = self._make_patient_so(submit=True)

        batch = frappe.get_doc(
            {
                "doctype": "Batch",
                "item": self.item.name,
                "supplier_batch_no": "PSO-B4",
                "nir_mrp": 300.0,
                "expiry_date": add_days(today(), 365),
                "nir_approval_status": "Approved",
            }
        ).insert()

        # Stock the store warehouse first
        se_stock = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "purpose": "Material Receipt",
                "stock_entry_type": "Material Receipt",
                "company": "_Test Company",
                "posting_date": today(),
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 10.0,
                        "t_warehouse": self.store_wh.name,
                        "batch_no": batch.name,
                        "basic_rate": 200.0,
                    }
                ],
            }
        ).insert()
        se_stock.submit()

        si = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer.name,
                "company": "_Test Company",
                "posting_date": today(),
                "nir_is_patient_special_order": 1,
                "nir_patient_sales_order": so.name,
                "nir_doctor_name": "Dr. A. K. Sharma",
                "nir_doctor_reg_no": "KA-12345-M",
                "nir_prescription": "/files/rx_test.pdf",
                "items": [
                    {
                        "item_code": self.item.name,
                        "qty": 5.0,
                        "rate": 300.0,
                        "batch_no": batch.name,
                        "warehouse": self.store_wh.name,
                    }
                ],
            }
        ).insert()
        si.submit()

        so.reload()
        self.assertEqual(so.nir_pso_status, "Completed")
