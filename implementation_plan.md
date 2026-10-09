# Pharmacy App — Implementation Plan & Status

**Status as of October 2026.** Bench: Frappe 16.31.0, ERPNext 16.8.0, India Compliance v16.6.1, Site: `pharmacy.local`.

---

## 1. Master Requirement Status Matrix (MD-01 to MD-11)

| ID | Priority | Status | What's Built | Primary Implementation Files |
|---|---|---|---|---|
| **MD-01** | Must | **Done** | Brand, salt, strength, dosage form, manufacturer, marketer; Box → Strip → Tablet; HSN; GST 0/5/18%; barcodes | [`install.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py), [`doctype/salt/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/salt/) |
| **MD-02** | Must | **Done (except registers)** | Category field; Rx flag set automatically; category drives licence checks, cage storage & Rx-at-sale. H1/X registers pending | [`overrides/item.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/item.py), [`overrides/prescription.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/prescription.py) |
| **MD-03** | Must | **Done for bins** | Storage condition on Item and Warehouse, checked when stock goes into a warehouse. Packing rules not built | [`overrides/storage.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/storage.py), [`install.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py) |
| **MD-04** | Must | **Done** | `Replenishment Schedule`: frequencies (`Daily`, `Alternate Days`, `Twice a Week`, `Weekly`, `Fortnightly`), `order_days`, hierarchical overrides (`Store` > `Cluster` > `All Stores` and `Item` > `Item Group` > `ABC Class` > `Global`) | [`doctype/replenishment_schedule/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/replenishment_schedule/) |
| **MD-05** | Should | **Done** | `get_substitutes(item_code, warehouse=None)`: returns active items matching salt (`nir_salt`) and strength (`nir_strength`), prioritizing private-label equivalents (`is_private_label=1`), with optional live warehouse stock availability | [`substitutes.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/substitutes.py), [`test_substitutes.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/test_substitutes.py) |
| **MD-06** | Must | **Done** | `Shelf Life Rule` (by item group or regulatory category); enforced on supplier receipts & store dispatches | [`doctype/shelf_life_rule/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/shelf_life_rule/), [`overrides/shelf_life.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/shelf_life.py) |
| **MD-07** | Must | **Done** | `Supplier` master: wholesale drug licences (Form 20B/21B/20G/etc.), GSTIN, FSSAI (`nir_fssai_no`), payment terms, lead time (`nir_lead_time_days`), MOQ (`nir_moq_value`, `nir_moq_qty`), expiry-return policy (`nir_expiry_return_window_days`, `nir_expiry_credit_pct`, `nir_expiry_return_policy`) | [`doctype/drug_licence/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/drug_licence/), [`install.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py), [`test_supplier_master.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/test_supplier_master.py) |
| **MD-08** | Must | **Done** | Store master (`Pharmacy Store`), clusters (`Cluster`), routes, store grades (A/B/C/D), pincode serviceability (`Pharmacy Store Pincode`), drug licence & GSTIN links | [`doctype/pharmacy_store/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/pharmacy_store/), [`doctype/cluster/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/cluster/) |
| **MD-09** | Must | **Done** | Warehouse roles, 7 zone types, bin capacity checked at submit | [`install.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py), [`overrides/storage.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/storage.py) |
| **MD-10** | Must | **Done** | Daily 30/15/7-day alerts & expiry status; transactions blocked by drug licence matrix | [`doctype/drug_licence/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/drug_licence/), [`overrides/party_licence.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/party_licence.py) |
| **MD-11** | Should | **Done** | Maker-checker approval workflow for new items, MRP/price changes, replenishment schedules & party masters | [`overrides/maker_checker.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/maker_checker.py), [`overrides/test_maker_checker.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/test_maker_checker.py) |

---

## 2. Implementation Guide & Code Mapping

### MD-01 — Item Master Data
* **Custom Fields**: Added via [`install.py → CUSTOM_FIELDS`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py#L38-L95) (`nir_salt`, `nir_strength`, `nir_marketer`, `nir_loose_sale`, `nir_nppa_controlled`).
* **UOMs**: Box, Strip, Tablet (whole numbers) created via [`create_uoms()`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/install.py#L125-L131).
* **DocType**: [`Salt`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/salt/salt.json) (`salt_name`, `strength`, `dosage_form`).
* **Test Suite**: [`test_salt.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/salt/test_salt.py)

### MD-02 — Regulatory Classification & Rx Validation
* **Custom Field**: `nir_regulatory_category` (`OTC`, `Schedule H`, `Schedule H1`, `Schedule X`, `NDPS`, `Cosmetic`, `FSSAI`).
* **Auto-set Hook**: [`overrides/item.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/item.py) automatically sets `nir_rx_required = 1` for `Schedule H`, `Schedule H1`, `Schedule X`, `NDPS`.
* **Sales Validation**: [`overrides/prescription.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/prescription.py) blocks submission of Sales Invoice / POS Invoice containing Rx items unless doctor details and prescription attachment are provided.
* **Test Suites**: [`overrides/test_item.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/test_item.py), [`overrides/test_prescription.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/test_prescription.py)

### MD-03 & MD-09 — Storage Conditions, Warehouse Layout & Bin Capacity
* **Warehouse Layout**: `nir_warehouse_role` (`DC`, `Zone`, `Bin`, `Store`, `Transit`, `Quarantine`, `Returns`, `Expired`), `nir_storage_condition` (`Ambient`, `Below 25C`, `2-8C`), `nir_bin_capacity`.
* **Validation Hook**: [`overrides/storage.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/storage.py) enforces:
  * Cold chain rules (`2-8C` and `Below 25C` item storage).
  * Scheduled drug cage restriction (Schedule X and NDPS items restricted to *Scheduled Drug Cage* zones).
  * Bin capacity checks on stock transaction submission.
* **Test Suite**: [`overrides/test_storage.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/test_storage.py)

### MD-04 — Replenishment Schedules, Store Replenishment Engine & Indents
* **DocType**: [`Replenishment Schedule`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/replenishment_schedule/replenishment_schedule.json) (`scope`: `All Stores`/`Cluster`/`Store`, `applies_to`: `Item`/`Item Group`/`ABC Class`/`Global`, `frequency`: `Daily`/`Alternate Days`/`Twice a Week`/`Weekly`/`Fortnightly`, `order_days`, `min_qty`, `max_qty`, `target_days_of_cover`, `lead_time_days`).
* **Calculation Engine**: [`pharmacy/replenishment.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/replenishment.py):
  * Dynamic schedule evaluation (`is_item_due_on_date`).
  * 3-tier hierarchy (`Store` > `Cluster` > `All Stores` & `Item` > `Item Group` > `ABC Class` > `Global`).
  * Velocity, Live Stock, In-Transit Stock, and Target calculation (Min/Max or Days of Cover).
  * Auto-generation of single draft `Material Request` per store/day and single delivery `Stock Entry`.
* **Manual Store Indents & Area Manager Approval**: [`pharmacy/overrides/material_request.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/material_request.py):
  * Off-schedule / manual store indents exceeding store's `nir_manual_indent_limit` require Area Manager approval (`approve_manual_store_indent`).
* **Patient Special Orders**: [`doctype/patient_special_order/`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/patient_special_order/):
  * Priority tracking of patient special requests for non-stocked items across Purchase (`Purchase Order`), DC Receipt (`Purchase Receipt`), Store Dispatch (`Stock Entry`), and Patient Pickup (`Sales Invoice`).
* **Test Suites**: [`pharmacy/test_replenishment.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/test_replenishment.py), [`overrides/test_material_request.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/overrides/test_material_request.py), [`doctype/patient_special_order/test_patient_special_order.py`](file:///Users/apple/frappe16-bench/apps/pharmacy/pharmacy/pharmacy/doctype/patient_special_order/test_patient_special_order.py)


---

## 3. Test Runner & Verification Command

To run the complete pharmacy test suite (114 integration tests currently passing):

```bash
bench --site pharmacy.local run-tests --app pharmacy
```

To run a targeted test module:
```bash
bench --site pharmacy.local run-tests --module pharmacy.overrides.test_party_licence
```

---

## 4. Remaining Phases Roadmap

1. **Phase D — Store Master & Replenishment (MD-04, MD-08)**:
   * `Cluster` & `Pharmacy Store` DocTypes.
   * `Replenishment Schedule` matrix (Store, Cluster, All-Store hierarchy).
   * Pincode serviceability lookup for online orders.
2. **Phase E — Maker-Checker Approval (MD-11)**:
   * Frappe Workflow integration on Item, Price, Supplier, Customer, Store.
   * Maker approval restriction (`nir_maker != session.user`).
   * Lock on master records until approved.
3. **Statutory Registers**:
   * Schedule H1, Schedule X, and NDPS statutory register script reports.
