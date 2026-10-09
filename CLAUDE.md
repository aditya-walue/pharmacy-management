# Pharmacy App — Implementation Overview & UI Testing Guide

**Bench**: Frappe 16.31.0, ERPNext 16.8.0, India Compliance v16.6.1  
**Site**: `pharmacy.local`  
**Web Port**: `http://localhost:8001` (or `http://pharmacy.local:8001`)

---

## 1. Core Implementations Completed

| Component | What Was Implemented | DocTypes / Code Location |
|---|---|---|
| **1. PO Approval Matrix & Warehouse/Supplier POs** | Single-warehouse per PO validation, multi-tier approvals based on order value and item category (`NDPS`, `Schedule X`, `Schedule H1`, `All Items`), approval buttons in UI, maker-checker prevention, and supplier dispatch/acknowledgement. | [`PO Approval Matrix`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/po_approval_matrix/), [`PO Approval`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/po_approval/), [`po_approval.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/po_approval.py), [`purchase_order.js`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/public/js/purchase_order.js) |
| **2. Warehouse Purchase Suggestions Engine** | DC purchase suggestions calculated from combined store consumption + online Sales Orders, lead time, safety stock days, open POs, MOQ rounding, and automatic supplier schemes. | [`Purchase Suggestion`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/purchase_suggestion/), [`Supplier Scheme`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/supplier_scheme/), [`purchase_suggestion_engine.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/purchase_suggestion_engine.py) |
| **3. Patient Special Orders** | Priority tracking for non-stocked patient items directly embedded on Sales Order (`nir_is_patient_special_order`, Patient Name, Phone, Store, Priority) linked to downstream PO, PR, and delivery. | [`install.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py), [`patient_order.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/patient_order.py) |
| **4. Store Replenishment & Indents** | Store schedules (`Daily`, `Alternate Days`, `Twice a Week`, `Weekly`, `Fortnightly`), order days, days-of-cover / min-max logic, and off-schedule indent approval by Area Manager. | [`Replenishment Schedule`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/replenishment_schedule/), [`replenishment.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/replenishment.py), [`material_request.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/material_request.py) |
| **5. Shelf Life Rules** | Enforced minimum remaining shelf life by Category / Item Group for Supplier Receipts vs Store Dispatches. | [`Shelf Life Rule`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/shelf_life_rule/), [`shelf_life.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/shelf_life.py) |
| **6. Regulatory Compliance & Rx Validation** | Form 20/20B/21B drug licence matrix; retail Rx validation blocking Sales Invoices unless doctor & prescription details are provided; Scheduled drug cage storage. | [`Drug Licence`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/drug_licence/), [`party_licence.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/party_licence.py), [`prescription.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/prescription.py), [`storage.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/storage.py) |

---

## 2. Step-by-Step UI Testing Guide

### 1. Test PO Approval Matrix & POs Raised by Warehouse and Supplier

#### A. View Configured Rules:
1. In the Awesomebar, navigate to **`PO Approval Matrix List`** (`/app/po-approval-matrix`).
2. Notice the pre-seeded rules categorized by regulatory category (`Schedule X`, `Schedule H1`) and value tiers (0–50K `Buyer`, 50K–250K `Purchase Manager`, >250K `Pharmacy Management`).

#### B. Test PO Creation & Approval Enforcement:
1. Go to **`Purchase Order`** → **`Add Purchase Order`** (`/app/purchase-order/new`).
2. Select:
   - **Supplier**: Select an active supplier (e.g. `_Test Supplier`).
   - **Set Warehouse**: Select a DC or Store warehouse.
   - **Items**: Add an item (e.g., standard item or Schedule H1 / Schedule X item) with quantity and rate.
3. Click **Save**:
   - The PO automatically checks that all lines go to the single selected warehouse.
   - The **Approvals** section appears on the form showing the required level, approver role (e.g. `Buyer`, `Purchase Manager`, or `Compliance Pharmacist`), and reason.
   - `Approval Status` becomes **`Pending`**.
4. Try clicking **Submit**:
   - ERPNext will block submission with an alert: *"This Purchase Order needs approval before it can be submitted. Waiting for Level 1: [Role]"*.
5. **Approve the Order**:
   - Under the top **Approval** dropdown button, click **`Approve`** (or **`Reject`** with remarks).
   - *Note*: Maker-checker ensures the creator cannot approve their own order unless logged in with an administrative role.
   - Once approved, status changes to **`Approved`** and the PO can be submitted.

---

### 2. Test DC Purchase Suggestions Engine

1. In the Awesomebar, search for **`Purchase Suggestion List`** (`/app/purchase-suggestion`).
2. Click **`Add Purchase Suggestion`**:
   - **Warehouse (DC)**: Select your Distribution Centre (e.g. `_Test Warehouse Group-C1 - _TC`).
   - **Demand Period (Days)**: `30` (defaults to 30 days of sales history).
   - **As of Date**: Today.
3. Click **Save** (creates the suggestion header in Draft).
4. Click the **`Generate Suggestions`** button on top:
   - The engine aggregates store demand from linked pharmacy stores, online demand from open Sales Orders, in-transit open POs, safety stock days, and rounds up to the supplier MOQ.
   - It also queries **`Supplier Scheme`** to auto-apply volume discounts or free goods.
   - The **Suggested Items** table is populated with ordered quantities, lead times, and rates.
5. Click **Submit**.
6. Click **`Create Purchase Orders`**:
   - The engine automatically groups items by `preferred_supplier` and creates separate Draft Purchase Orders per supplier with the target DC warehouse already set.

---

### 3. Test Patient Special Orders in Sales Order

1. Go to **`Sales Order`** → **`Add Sales Order`** (`/app/sales-order/new`).
2. Check the box **`Patient Special Order`** (`nir_is_patient_special_order`):
   - The **Patient & Store Information** section becomes visible:
     - **Patient Name**: Enter patient name.
     - **Patient Phone**: Enter patient contact number.
     - **Pharmacy Store**: Select store.
     - **Priority**: Select `High` / `Urgent`.
3. Add the non-stocked item and save/submit.
4. When raising a Purchase Order or Stock Entry for this item, check `Patient Special Order` and link the Sales Order; the system tracks the item as high priority through DC receipt, store transfer, and patient pickup.

---

### 4. Test Store Replenishment Schedules & Off-Schedule Indents

1. Navigate to **`Replenishment Schedule List`** (`/app/replenishment-schedule`).
2. View or create schedules specifying:
   - **Scope**: `Store`, `Cluster`, or `All Stores`.
   - **Applies To**: `Item`, `Item Group`, or `Global`.
   - **Frequency & Order Days**: e.g., `Weekly` on Monday and Thursday.
   - **Target Days of Cover** or **Min/Max Stock**.
3. Create a **`Material Request`** (Material Transfer) for a store:
   - If items outside the schedule are ordered and the indent value exceeds the store's **`Manual Indent Approval Threshold`**, Area Manager approval is required before the indent can be submitted.

---

### 5. Test Minimum Remaining Shelf Life

1. Navigate to **`Shelf Life Rule List`** (`/app/shelf-life-rule`).
2. View rules configured by Item Group or Regulatory Category:
   - e.g. Supplier Receipt Rule: Minimum 75% remaining shelf life.
   - Store Dispatch Rule: Minimum 50% remaining shelf life.
3. In **`Purchase Receipt`** or **`Stock Entry` (Material Transfer)**:
   - Attempting to receive a batch with remaining shelf life below the rule threshold will raise a validation error blocking receipt or dispatch.
