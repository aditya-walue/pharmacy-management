# Pharmacy App — Implementation Overview & UI Testing Guide

**Bench**: Frappe 16.31.0, ERPNext 16.8.0, India Compliance v16.6.1
**Site**: `pharmacy.local`
**Web**: `http://127.0.0.1:8001` (or `http://pharmacy.local:8001`)
**Desk**: open the **Pharmacy** tile on `/desk`; its sidebar and workspace link every doctype below.

> Keep this guide current: add or update a section after every module is implemented.
> **Last updated:** 2026-10-08 — covers modules 1–26 (master data, purchasing, inbound, storage & inventory control WH-01 to WH-06, DC outbound, routes & trips, tote tracking, store receiving & transfers ST-01 to ST-05, store billing POS-01 to POS-04).

---

## How the System Works

The system follows medicines from **supplier → DC (central warehouse) → trip → store → patient**. Every step is an ERPNext document; the pharmacy rules run automatically when it is saved or submitted. Master data and compliance sit underneath all of it.

```
SUPPLIER ──PO──▶ DC ──Pick Wave──▶ TRIP ──▶ STORE ──POS──▶ PATIENT
            ▲                                   │
            └──── store sales = demand ─────────┘
```

### The Four Core Business Flows

The platform orchestrates the end-to-end pharmaceutical supply chain from supplier procurement to DC distribution, retail store dispensing, and online e-commerce fulfillment. Every workflow is governed by strict compliance, maker-checker segregation, and multi-tier role-based approvals.

#### Flow 1 — Store Replenishment to Store Receipt

| Step | Screen / Document | Implementation Details | Approver & Authority (Who Approves) |
|---|---|---|---|
| **Replenishment Schedule** | `Replenishment Schedule` | Configures ordering frequency, order days, and weekly ceilings per store, cluster, or item group. | **Category Manager** (Configured once; edits require Maker-Checker sign-off) |
| **Store Replenishment Suggestions** | `Replenishment Schedule` / `Material Request` | Generates replenishment indents based on store min/max, in-transit shipments, and average daily consumption. | Auto-calculated; Store Pharmacist reviews |
| **Store Indent Submission** | `Material Request` (Material Transfer) | Regular scheduled store indents move directly to DC pick waves. Indents raised off-schedule or exceeding weekly quotas require approval. | **Area Manager** (or **Pharmacy Management**) for off-schedule indents |
| **DC Purchase Suggestion Engine** | `Purchase Suggestion` | Consolidates demand across retail stores + online Sales Orders, lead time, safety stock (A/B/C), open POs, supplier MOQ, and supplier schemes. | **Buyer** triggers calculation; **Warehouse Manager** validates quantities |
| **Purchase Order Creation & Approval** | `Purchase Order`, `PO Approval Matrix`, `PO Approval` | Automatically splits suggestions into per-supplier POs priced from rate contracts (PTR − trade discount) with 10+1 free schemes. Evaluates multi-tier approval matrix. Maker-checker strictly enforced. | **Buyer** (≤ ₹50k)<br>**Category Manager** (₹50k–₹2L)<br>**Warehouse Manager** (₹2L–₹10L)<br>**Pharmacy Management** (> ₹10L)<br>**Compliance Pharmacist** (Mandatory for NDPS & Schedule X) |
| **Supplier Notification & Dispatch** | `Purchase Order`, Supplier Portal | PO PDF automatically emailed to supplier. Supplier logs in to acknowledge PO with committed delivery date. Backorders tracked automatically. | System-automated via Frappe Email Queue |
| **Gate Entry & Inbound QC** | `Gate Entry`, `Purchase Receipt` | Security logs vehicle arrival and cases. Pharmacist scans barcodes/batches; verifies expiry, MRP ceiling (NPPA), and cold-chain temperature. Temperature breaches move to quarantine. | **Inward QC Executive** / **Store Pharmacist**; Quarantine disposition by **Compliance Pharmacist** |
| **Put-away to DC Storage** | `Put-away List` | System directs stock to optimal bins by zone, temperature requirements (2–8°C vs Ambient), and bin capacity limits. | Warehouse Staff scan batch and target bin to confirm |
| **FEFO Picking & Tote Allocation** | `Pick Wave` | Groups store indents by delivery route. Allocates earliest-expiry batches matching store shelf-life rules. Packed into barcoded returnable totes and validated ice boxes. | **Picker Packer** and **Dispatch Coordinator** |
| **Dispatch & e-Way Bill** | `Dispatch Trip`, `Delivery Note` | Multi-stop dispatch trips with delivery sequence and load manifests. Generates statutory delivery challans or tax invoices with IRN and e-way bill via India Compliance. | **Dispatch Coordinator** authorizes trip departure |
| **Store Inwarding & Discrepancy** | `Store Receipt`, `Transfer Discrepancy` | Store pharmacist scans received totes and validates security seals. Variances logged within 24 hours generate a Transfer Discrepancy note. | **Store Pharmacist** logs receipt; Discrepancy sign-off by **Warehouse Manager** |

#### Flow 2 — Counter Sale & POS Retail Billing

| Step | Screen / Document | Implementation Details | Approver & Authority (Who Approves) |
|---|---|---|---|
| **Customer Prescriptions & Patient Search** | Point of Sale / `Customer Prescription` | Pharmacist verifies customer, pulls existing patient records, or registers new patient with doctor registration details. | **Store Pharmacist** (Validates doctor registration & Rx validity) |
| **Medicine Selection & Salt Substitution** | POS Screen → **Pharmacy Search** | Instant modal search by Brand, Active Generic Salt, Strength, or Barcode. Shows real-time batch stock, expiry date, MRP, and generic substitutes. | Pharmacist dispenses matching molecule |
| **Batch Allocation by FEFO** | `POS Invoice` / `Sales Invoice` | System enforces earliest-expiry batch selection. Blocks expired batches, quarantined lots, or recalled batches (via `Stock Hold`). | System-enforced FEFO algorithm |
| **Discount Controls & Margin Protection** | `POS Discount Limit`, `Pricing Rule` | Automatic promotional discounts applied via Pricing Rules. Manual discounts capped strictly by user role (e.g. Pharmacist ≤ 5%, Area Manager ≤ 20%). | Discounts above cashier threshold require **Store Pharmacist** or **Area Manager** approval |
| **GST Billing & Controlled Drug Entry** | `POS Invoice`, `Controlled Drug Register` | Generates tax-inclusive invoice adhering to NPPA ceiling limits. Any sale of Schedule H1 or Schedule X updates the statutory register in real-time. | **Store Pharmacist** signs off invoice; Register entries locked to **Compliance Pharmacist** |

#### Flow 3 — Online Order Portal, Dedicated Cart & Razorpay Checkout

| Step | Screen / Document | Implementation Details | Approver & Authority (Who Approves) |
|---|---|---|---|
| **Online Medicine Catalog** | `/order` (Frappe Builder) | Streamlined pharmacy catalog showing essential clinical details only (*Active Generic Salt*, *Strength*, *Form/Packaging*, *Rx/OTC Tag*, *Price*), clinical department tabs, and dosage filters. | Customer self-service; Real-time pricing from Item Price |
| **Dedicated Shopping Cart** | `/cart` (Frappe Builder) | Comprehensive cart review table with quantity modifiers, active chemical formulas, fulfillment selector (Home Delivery with Pincode or Store Pickup with Store locator). | Customer self-service |
| **Prescription Capture & Special Indent** | `/cart` | Optional prescription upload for Schedule H/H1 medicines. Optional toggle for **Patient Special Order** for emergency non-stocked pharmaceuticals. Attached prescription file is saved against the Sales Order for pharmacist reference. | Customer attaches prescription |
| **Payment Gateway & Auto-Billing** | `/cart` → Razorpay SDK | Direct integration with **Razorpay Secure Checkout** (`checkout.js`). Upon successful payment, automatically submits Sales Order, generates and submits official GST **Sales Invoice**, and posts **Payment Entry** (Status: Paid). Also supports Cash on Delivery (COD). | Razorpay automated webhook / signature verification; Backend auto-billing |
| **Customer Orders & Tax Invoices Page** | `/orders` (Frappe Builder) | Real-time customer tracking page: searches orders by phone, email, or order ID; displays status pills, fulfillment tracking, and interactive modal to view & print official GST Sales Invoices. Includes direct Razorpay pay button for pending orders. | Customer self-service |
| **Automated Customer Email Updates** | `pharmacy.online.order_notifications` | Branded HTML emails dispatched automatically to customer email upon order placement, payment confirmation, and status changes (*Confirmed*, *Dispatched*, *Delivered*). | System-automated via Frappe Email Queue |
| **Fulfillment & Batch Picking** | `Sales Order` → `Sales Invoice` / `Delivery Note` | Auto-allocates order lines to nearest retail store with inventory. Store picks earliest-expiry batches via FEFO and hands over to rider/patient. Pharmacist can view uploaded prescription directly from the Sales Order form via **View Prescription**. | **Store Pharmacist** dispenses and validates batches |

#### Flow 4 — Store Returns & Supplier Credit

| Step | Screen / Document | Implementation Details | Approver & Authority (Who Approves) |
|---|---|---|---|
| **Store Return Indent** | `Stock Entry` (Material Transfer / Return) | Retail store initiates return of near-expiry, slow-moving, or damaged stock back to DC. | **Store Pharmacist** initiates; **Area Manager** approves return request |
| **DC Quality Inspection & Quarantine** | `Quarantine Decision` | Inward QA inspects returned lots: verifies seals, physical condition, and expiry window against supplier return agreements. | **Compliance Pharmacist** or **Inward QC Executive** |
| **Disposition Decision** | `Quarantine Decision` | Determines lot disposition: return to supplier for credit, return to active stock, or quarantine for statutory destruction. | **Warehouse Manager** & **Compliance Pharmacist** |
| **Supplier Debit Note & Credit Settlement** | `Purchase Invoice` (Debit Note) | Generates debit note to supplier adhering to contractual expiry-return windows and credit percentages. | **Pharmacy Accounts** (Reviews and submits debit note) |

---

### System-Wide Approval & Governance Matrix

| Business Area | Transaction / Document | Approval Condition & Trigger | Who Must Approve (Role) | Maker-Checker Rule | UI Action & Enforcement |
|---|---|---|---|---|---|
| **Procurement** | `Purchase Order` | Tier 1: Value ≤ ₹50,000 (Non-scheduled items) | **Buyer** | Creator cannot approve own PO | PO Toolbar: **Approve / Reject** buttons. Unapproved POs blocked from submit. |
| **Procurement** | `Purchase Order` | Tier 2: ₹50,001 to ₹2,00,000 | **Category Manager** | Creator cannot approve own PO | PO Toolbar: **Approve / Reject** buttons. |
| **Procurement** | `Purchase Order` | Tier 3: ₹2,00,001 to ₹10,00,000 | **Warehouse Manager** | Creator cannot approve own PO | PO Toolbar: **Approve / Reject** buttons. |
| **Procurement** | `Purchase Order` | Tier 4: Value > ₹10,00,000 | **Pharmacy Management** | Creator cannot approve own PO | PO Toolbar: **Approve / Reject** buttons. |
| **Procurement** | `Purchase Order` | Regulatory: Contains Schedule X or NDPS items | **Compliance Pharmacist** (Mandatory regardless of value) | Creator cannot approve own PO | PO Toolbar: **Approve / Reject** buttons. |
| **Procurement** | `Purchase Order` | Regulatory: Contains Schedule H1 antibiotics | **Category Manager** or **Compliance Pharmacist** | Creator cannot approve own PO | PO Toolbar: **Approve / Reject** buttons. |
| **Master Data** | `Item`, `Supplier`, `Customer`, `Item Price`, `Replenishment Schedule`, `Pharmacy Store`, `Batch` | New master created or critical fields modified (rates, licences, categories) | **Pharmacy Management** or **Compliance Pharmacist** | Maker cannot approve own master | Form toolbar: **Approve Master** action. Transactions blocked until approved. |
| **Replenishment** | `Material Request` (Store Indent) | Off-schedule order (outside designated store days) or order exceeding weekly quota | **Area Manager** (or **Pharmacy Management**) | Store Pharmacist cannot self-approve off-schedule requests | Material Request: **Approve Indent** button required before DC picking. |
| **Retail POS** | `POS Invoice` / `Sales Invoice` | Cashier manual discount exceeds standard limit (e.g., > 5%) | **Store Pharmacist** (up to 20%) or **Area Manager** (above 20%) | Cashier cannot approve own discount | POS modal prompts supervisor PIN / authorization. |
| **Physical Inventory** | `Stock Count` / `Stock Reconciliation` | Cycle count or audit discrepancy between physical count and system ledger | Up to threshold: **Warehouse Manager**; Above threshold or scheduled drugs: **Compliance Pharmacist** / **Pharmacy Management** | Count taker cannot approve variance | Stock Count submission triggers approval workflow before ledger adjustment. |
| **Inbound Quality** | `Quarantine Decision` | Temperature breach (cold-chain), damaged goods, or failed visual QC | **Compliance Pharmacist** (for medicines) or **Warehouse Manager** (for FMCG) | Receiving staff cannot make QA decision | Quarantine Decision: **Submit** releases stock or initiates debit note. |
| **Online Rx Orders** | `Sales Order` | Online order containing Schedule H, H1, or Rx required medication | **Online Order Pharmacist** (or **Store Pharmacist**) | Pharmacist inspects uploaded doctor prescription before fulfillment | Sales Order → **Prescription → View Prescription** button opens attached document. |
| **Controlled Drugs** | `Controlled Drug Register` | Movement, receipt, internal transfer, or destruction of Schedule X / NDPS stock | **Compliance Pharmacist** (Licensed Drug Custodian) | Strict custody log; two-person verification for destruction | Statutory register updated; requires custodian credential verification. |

---
3. **Create Purchase Orders** → one PO per supplier, priced from the **rate contract** (PTR − trade discount), schemes (10+1 free) applied.
4. **PO Approval Matrix** decides who must approve, by value and category; the creator can never approve. Supplier and DC **drug licences** are checked.
5. On submit the PO PDF is **emailed**; the supplier **acknowledges** on the portal with a delivery date. Late or short supplies are followed up automatically; supplier fill rate and lead time are tracked.

#### How a purchase suggestion is calculated

All quantities in stock units (e.g. tablets):

| Step | Rule |
|---|---|
| Items considered | In stock anywhere in the DC, sold by stores served by the DC in the period, on an open PO to the DC, or on an open online Sales Order from the DC |
| Demand | Units sold by the served stores (Sales + POS Invoices) in the period **+** undelivered qty on open online orders |
| Daily demand | Demand ÷ period days |
| Lead time | Preferred supplier's lead time → else the Item's → else 7 days |
| Safety days | Item *Safety Stock Days* → else by ABC class: **A 7, B 14, C 30** |
| Required | Daily demand × (lead time + safety days) |
| Available | DC stock (all bins) + qty still due on open POs |
| Order qty | Required − Available, rounded **up** to MOQ (Supplier MOQ → else Item *Min Order Qty*); none if ≤ 0 |
| Free goods / discount | Supplier Scheme at that qty: free = order × ratio, or % off the rate |
| Value | Last PO rate from the supplier (else Item last purchase rate), less scheme discount, × order qty |

Worked examples (demo data):

- **Pan 40** (ABC A, Apex 3-day lead, MOQ 150): 1,800 sold in 30 days → 60/day; required 60 × (3 + 7) = 600; available 150 → order **450** (3 boxes) ≈ ₹3,300.
- **Dolo 650** (ABC A, scheme 10+1 from 450): 89.6/day → required 896; available 300 → 596 → MOQ → **600** + **60 free**.
- **Ensure 400 g** (ABC B, 7-day lead, MOQ 12): 60 sold + 12 online = 72 → 2.4/day; required 2.4 × 21 = 50.4; available 6 → **48**.
- **Calpol 500**: 2,000 in stock covers the need → **no suggestion**.

**Generate Suggestions** fills the table (highest value first; *Ordered Qty* can be edited) → **Submit** → **Create Purchase Orders** groups lines by preferred supplier into draft POs (lines without a supplier are skipped). To change results: supplier lead time, item ABC class / Safety Stock Days, Min Order Qty or supplier MOQ, supplier schemes, or the period.

### 2. Receive at the DC
1. **Gate Entry**: PO, vehicle, supplier invoice no. and number of cases logged at the gate.
2. **GRN** (Purchase Receipt, *Scan & Receive*): supplier batch, expiry, MRP and free qty per line; batches created automatically.
   - **Blocked**: not on the PO, more than ordered, short shelf life, MRP above the NPPA ceiling.
   - **Approval**: MRP different from the last batch.
   - **Cold chain**: temperature breach → **Quarantine** for a QA decision.
   - **Schedule X / NDPS** → straight into the **locked cage**; **Controlled Drug Register** written.
   - Damage / shortage / excess → **discrepancy note** to the supplier.
3. **Put-away**: system suggests the bin by zone, temperature and capacity; staff confirm by scanning. Batch and bin labels printed.
4. **Supplier invoice**: **three-way match** with PO and GRN; rate or qty differences raise draft **debit notes**.

### 3. Keep stock right (DC and stores)
- **Pick faces** topped up hourly from reserve stock, earliest expiry first.
- **Stock counts**: ABC cycle counts and full counts, blind on the handheld; variances approved.
- **Adjustments** need a reason code and an approver.
- **Stock holds** (QC, recall, legal) and **quarantine** stop stock being picked or sold.
- **Alerts and reports**: near-expiry at 180/90/60/30 days; slow-moving, ageing and valuation reports.

### 4. Ship to stores
1. **Pick Wave**: due indents grouped by **delivery route**; stock allocated earliest expiry first, meeting the store's minimum shelf life, with few batches per line.
2. **Handheld picking** by zone: scan bin → batch → qty → tote. Cold items only into **ice boxes**, scheduled drugs only into **scheduled-drug totes**. **Short picks**: backorder, substitute (same salt and strength) or cancel; the store is told.
3. **Seal** totes → **Dispatch**:
   - same GSTIN → **delivery challan** (stock moves into transit);
   - different GSTIN or company → **tax invoice** (IRN and e-way bill via India Compliance);
   - scheduled drugs on a separate document with register entries.
4. **Dispatch Trip**: vehicle and driver, stops in route order; totes scanned onto the truck → **Depart** (writes vehicle details for the e-way bill) → trip sheet. Each **delivered stop** puts its totes in that store's custody.

### 5. Store
1. **Shipments in Transit**: what is coming and when.
2. **Store Receipt**: scan totes, check seals; tote-level check or full count depending on the store; stock moves from transit into the store.
3. Differences within 24 hours → **Transfer Discrepancy**: store reports, DC investigates, approver signs off, stock adjusted. After 24 hours the shipment counts as received in full.
4. **Store-to-store transfers** for a patient's need or to balance stock, with approval.
5. Empty totes, crates and ice boxes go back on the next trip; missing ones are tracked by store.

### 6. Sell (POS)
- **Pharmacy Search** by barcode, brand or salt: stock, batches, expiry, MRP.
- Earliest-expiry batch picked by default; expired, held or recalled batches blocked.
- **Loose sale** of strips or tablets priced from the pack MRP.
- Price never above batch MRP; automatic discounts from Pricing Rules; manual discounts capped by role, with approval above the cap.
- Rx items need prescription and doctor details.
- Every sale updates store stock in real time, which feeds the next replenishment and purchase suggestion — closing the loop.

### What runs underneath

| Layer | Role |
|---|---|
| Masters | Items (salt, strength, category, storage, pack conversions, HSN/GST), batches (MRP, expiry), suppliers, stores, routes, warehouse zones and bins |
| Compliance | Drug licences checked on every purchase, sale and transfer, with expiry alerts; NPPA ceilings; Schedule X / NDPS cage and register; prescriptions |
| Maker-checker | Approvals on POs, MRP changes, adjustments, counts, discounts, transfers; the creator never approves |
| Background jobs | Hourly: PO reminders, pick-face top-ups, store auto-receive. Daily: licence alerts, backorder follow-ups, supplier performance, near-expiry and overdue-tote alerts |
| Roles | Buyer, Category Manager, Inward QC, Warehouse Manager, Picker / Packer, Dispatch Coordinator, Driver, Store Pharmacist, Area Manager, Compliance Pharmacist, Accounts, Management |

---

## Pharmacy Workspace Guide

Open the **Pharmacy** tile on `/desk`. The page has two parts:

- **Your Shortcuts** — one tile per screen. The number on a tile is how many records exist (e.g. *Drug Licence 119*, *NPPA Ceiling Price 14*, *Salt 17* come from the demo catalogue and test runs); report and page tiles have no count. Click a tile to open its list.
- **Masters & Reports** — the same screens grouped by area, in the same order as the left **sidebar** (Compliance → Stores & Replenishment → Purchasing → Inbound → Inventory Control → Outbound → Stores → Store Billing → Reports). **Home** in the sidebar returns to this page.

Type key: **Master** = set up once and maintained; **Transaction** = created in day-to-day work; **Log** = written by the system, read-only; **Report** = query screen; **Page** = special screen. **Test §N** = numbered section *N* under **2. Step-by-Step UI Testing** below.

### Compliance

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Drug Licence | Master | Drug / FSSAI licences (Form 20, 21, 20B, 21B, 20F, 20G, FSSAI…) with validity, for suppliers, customers, the DC and stores. Every purchase, sale and transfer is checked against them; alerts at 30/15/7 days | Compliance Pharmacist | §2 |
| NPPA Ceiling Price | Master | Government ceiling price per unit (excl. GST) for price-controlled items, with validity; batch MRP above ceiling × pack × (1 + GST) is refused | Compliance Pharmacist, Category Manager | §1 |
| Shelf Life Rule | Master | Minimum days of shelf life left, by item group or regulatory category: one figure for supplier receipts, one for dispatch to stores | Category Manager, Warehouse Manager | §3 |
| Salt | Master | Generic molecules (Paracetamol, Metformin…); items link to a salt + strength, which drives substitutes and POS salt search | Category Manager | §1, §26 |
| Controlled Drug Register | Log | Statutory Schedule X / NDPS register: every receipt, transfer and reversal with batch, party, invoice and running balance; cannot be edited or deleted | Compliance Pharmacist | §15 |

### Stores & Replenishment

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Pharmacy Store | Master | A store: its warehouse, serving DC, cluster, route, grade, GSTIN, licence, pincodes, internal customer, substitution and receiving-check settings | Area Manager, admin | §22, §25 |
| Cluster | Master | Group of stores under an Area Manager; replenishment schedules can apply to a cluster | Area Manager | §7 |
| Replenishment Schedule | Master | How often and on which days a store (or cluster / all stores) orders an item or item group; drives store indents | Category Manager | §7 |
| Purchase Suggestion | Transaction | DC buying proposal from store sales, online orders, stock, open POs, lead time, safety stock, MOQ and schemes → *Create Purchase Orders* (one per supplier) | Buyer | §5 |
| Patient Special Order | Transaction | Non-stocked item ordered for a named patient, tracked through PO, receipt and store hand-over | Store Pharmacist | §6 |

### Purchasing

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Purchase Order | Transaction | ERPNext PO with pharmacy additions: one warehouse per PO, approval matrix, contract pricing, email to supplier, acknowledgement, short close, fill rate & lead time | Buyer | §4, §8–§10 |
| PO Approval Matrix | Master | Who must approve a PO, by value range, regulatory category / item group, warehouse and level | Category Manager | §4 |
| Rate Contract | Master | ERPNext *Blanket Order* (Purchasing) with PTR and trade discount per item and validity dates; POs are priced from it | Category Manager | §8 |
| Scheme (Pricing Rule) | Master | ERPNext *Pricing Rule* for supplier schemes such as 10+1 free on purchases (and automatic discounts at POS) | Category Manager | §8, §26 |
| Supplier Scheme | Master | Pharmacy scheme record (quantity discount / free goods / cash discount) used by Purchase Suggestion estimates | Buyer | §5 |
| Supplier | Master | ERPNext supplier with lead time, MOQ, expiry-return terms, licences and 90-day performance (fill rate, on-time, actual lead time) | Buyer | §10 |

### Inbound

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Gate Entry | Transaction | Vehicle arrival at the DC: PO (fills supplier and DC), vehicle, driver, supplier invoice no., number of cases; required before any GRN | Inward QC Executive | §12 |
| Receipt Discrepancy | Transaction | Damage / shortage / excess on a supplier delivery, with photos; submitted note is emailed to the supplier | Inward QC Executive, Buyer | §12 |
| Quarantine Decision | Transaction | QA decision on quarantined stock (e.g. cold-chain breach): release, return to supplier, or destroy | Compliance Pharmacist, Warehouse Manager | §13 |
| Put-away List | Transaction | System-suggested bins for stock received into the Receiving zone; confirmed by scanning batch and bin | Warehouse staff | §14 |

### Inventory Control

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Stock Count | Transaction | ABC cycle count or full physical verification, counted blind on the handheld; variances approved before posting | Warehouse / store staff, Warehouse Manager | §18 |
| Stock Hold | Transaction | QC / Recall / Legal hold on an item, batch or location; held stock cannot be picked, billed or moved (except into holding zones) | Compliance Pharmacist, Warehouse Manager | §20 |
| Pick Face | Master | Pick bin + item with min / max; topped up hourly from reserve stock (earliest expiry first) | Warehouse Manager | §17 |
| Stock Adjustment Reason | Master | Reason codes required on every stock adjustment (Damage, Breakage, Expiry Write-off, Count Variance…) | Warehouse Manager | §19 |

### Outbound

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Pick Wave | Transaction | Store indents for one route and dispatch slot: FEFO allocation, handheld picking into totes, short picks, sealing, dispatch documents | Picker Packer, Dispatch Coordinator | §22 |
| Tote | Master | Returnable tote / crate / ice box / scheduled-drug box with barcode; status shows where it is (available, sealed, in transit, at store, missing) | Dispatch Coordinator | §22, §24 |
| Delivery Route | Master | Route from a DC with stores in delivery sequence, distance and travel time | Dispatch Coordinator | §23 |
| Dispatch Trip | Transaction | Vehicle (own / hired), driver, stops, tote load manifest, departure, deliveries, empties collected; prints Trip Sheet and Load Manifest | Dispatch Coordinator, Driver | §23, §24 |
| Tote Movement | Log | Every tote issued to, returned from, missing at or found at a store | Dispatch Coordinator | §24 |

### Stores

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Store Receipt | Transaction | Store receiving a shipment by tote scan (tote-level or full count), with damage and shortages, within the discrepancy window | Store Pharmacist | §25 |
| Transfer Discrepancy | Transaction | Store ↔ warehouse discrepancy: store reports, DC investigates, approver signs off, stock adjusted | Store Pharmacist, Warehouse Manager | §25 |
| Store Transfer Request | Transaction | Stock moved between stores for a patient or for balancing, with approval and challan / invoice | Store Pharmacist, Area Manager | §25 |

### Store Billing

| Screen | Type | What it is | Who uses it | Test |
|---|---|---|---|---|
| Point of Sale | Page | ERPNext POS with the **Pharmacy Search** button (barcode / brand / salt, batches, expiry, MRP, substitutes) | Store Pharmacist | §26 |
| POS Discount Limit | Master | Maximum manual discount per role and who may approve larger ones (seeded: Store Pharmacist 5%, Area Manager 20%, Pharmacy Management 30%) | Pharmacy Management | §26 |
| Pricing Rule | Master | Automatic discounts by item, item group, customer group or promotion dates | Category Manager | §26 |
| POS Invoice | Transaction | Store bills; batch, MRP, loose-sale and discount rules are applied on save | Store Pharmacist | §26 |

### Reports

| Report | What it shows | Test |
|---|---|---|
| Supplier Performance | Per supplier: POs, fill rates, average vs promised lead time, on-time %, short closes | §10 |
| Stock by Location | Stock by site / zone / bin / item / batch with expiry, MRP, value and age buckets | §16 |
| Near Expiry Stock | Batches expiring within N days, bucketed 30 / 60 / 90 / 180 | §21 |
| Slow and Non-Moving Stock | Items with no or slow outward movement, days of cover | §21 |
| Tote Balance by Store | Totes, crates and ice boxes issued, returned, held, overdue and missing per store | §24 |
| Shipments in Transit | Shipments on the way to each store with trip and expected arrival; *Receive Selected* starts a Store Receipt | §25 |
| Store Stock Overview | Live store stock, in transit, pending indents, sales rate and days of cover | §25 |

### Typical day, end to end

1. **Buy** — Purchase Suggestion → Purchase Orders → approval → emailed → supplier acknowledges on the portal.
2. **Receive at DC** — Gate Entry → Purchase Receipt (Scan & Receive) → quarantine / discrepancy if needed → Put-away List.
3. **Keep stock right** — Pick Face top-ups, Stock Counts, Stock Holds, adjustments with reasons; watch Near Expiry and Stock by Location.
4. **Ship to stores** — store indents → Pick Wave → pick into totes → seal → dispatch documents → Dispatch Trip.
5. **Store** — Shipments in Transit → Store Receipt → Transfer Discrepancy if anything is off → sell at Point of Sale.

---

## End-to-End Test Script (DC → Store → Bill)

Uses the demo data already on `pharmacy.local` (items, *Main DC - _TP*, *Store Andheri / Store Bandra*, suppliers, store sales). One full pass takes about 45 minutes.

**Two browser sessions.** Approvals never accept the creator (maker ≠ checker, even for Administrator). Work as a normal user in one window (the *maker*, e.g. a user with Buyer, Purchase User, Stock User, Store Pharmacist, Picker Packer, Dispatch Coordinator, Inward QC Executive) and approve as **Administrator** in a private window (the *checker*).

### Step 0 — one-time setup (≈10 min)

| What | Where | Value |
|---|---|---|
| Maker user | User → New | any email, roles listed above |
| In-transit warehouse | Company *_Test Pharmacy* → Default In-Transit Warehouse | *Goods In Transit - _TP* |
| Route | Delivery Route → New | *Route West*, DC *Main DC - _TP*, dispatch 10:00; stops 1 *Store Andheri* (8 km, 25 min), 2 *Store Bandra* (14 km, 40 min) |
| Totes | Tote → New | *T-001*, *T-002* (Standard), *ICE-001* (Insulated Cold Box), *SCH-001* (Scheduled Drugs) |
| Vehicle & driver | Vehicle, Driver | any licence plate; any driver with a mobile |
| POS Profile | POS Profile → New | company *_Test Pharmacy*, warehouse *Store Andheri - _TP*, price list *Standard Selling*, a cash payment mode, customer *Walk-in Customer*; taxes template with *Included in Print Rate* |
| Email (optional) | Email Account | default outgoing — otherwise PO / discrepancy emails show *Failed*, which is fine for testing |

### Step 1 — Buy: Purchase Suggestion → POs (§5, §4)

1. *Maker*: **Purchase Suggestion → New** → Warehouse *Main DC - _TP*, period 30, today → Save → **Generate Suggestions** (~13 lines; Dolo shows 60 free) → **Submit** → **Create Purchase Orders** → 3 draft POs (Apex, Coldline, Wellness).
2. Open the **Apex** PO → Save → *Approvals* table shows level(s) and roles; *Approval Status = Pending*. Try **Submit** → refused.
3. *Checker*: open the PO → **Approval → Approve** (each level) → *Approved*.
4. *Maker*: **Submit** → *PO Email Status* = Sent / Failed; **Supplier → Record Acknowledgement** with an expected delivery date.

### Step 2 — Receive at DC (§12, §14, §15)

1. **Gate Entry → New** → pick the **Purchase Order** → supplier, company and receiving DC (*Main DC - _TP*) fill in → vehicle no., **Supplier Invoice No** (the supplier's bill no., not the PO no.), **No. of Cases** → **Submit**.
2. On the submitted Gate Entry: **Create → Purchase Receipt** (or from the PO) → gate entry, supplier invoice no. and vehicle already filled in, leave the warehouse as the DC (*Main DC - _TP*) — on save each line is placed automatically: Schedule X / NDPS → *DC Cage*, 2-8°C → *DC Cold Room*, below-25°C → *DC General Cool*, everything else → *DC Receiving* (for put-away); the *Receipt Flags* say where. For each line fill *Supplier Batch No*, *Mfg / Expiry Date*, *MRP (per UOM)* — or use **Scan & Receive** (scan / type the item code). Save → check *Receipt Flags*.
3. Submit (as *checker* if the receipt has Alprazolam — cage custody). A **Put-away List** is created; Controlled Drug Register gets a *Receipt* line for Alprax.
4. **Put-away List** → **Scan Put-away** → batch label = batch name (e.g. `PAN-40-B1`), bin = the *Suggested Bin* → repeat for all lines → **Submit** → stock moves to the bins.
5. Optional: print **GRN Batch Labels** from the receipt and **Bin Label** from a warehouse.

### Step 3 — Indent and pick (§22)

1. *Maker*: **Material Request → New** → Purpose *Material Transfer*, Target Warehouse *Store Andheri - _TP*, Set Source Warehouse *Main DC - _TP*, Required By today, items e.g. PAN-40 60, DOLO-650 45 → **Submit**. Do the same for *Store Bandra*.
2. **Pick Wave** list → **Create Today's Waves** → Company, DC *Main DC - _TP* → wave for *Route West* with both indents and FEFO-allocated *Pick Lines*.
3. **Pick** → scan bin (*Pick From*), batch, qty, tote *T-001* for Andheri / *T-002* for Bandra (cold items → *ICE-001*, Schedule X / NDPS → *SCH-001*).
4. Optional short pick: **Pack → Resolve Short Lines** → *Mark short* → *Backorder / Substitute / Cancel*.
5. **Pack → Seal Tote** for every tote (seal no.; ice box also needs ice packs + temperature).
6. **Dispatch** → per store a **Stock Entry** delivery challan into *Goods In Transit* (or a Sales Invoice if GSTINs differ).

### Step 4 — Trip (§23, §24)

1. **Dispatch Trip → New** → today, *Route West*, Own vehicle, driver → Save → **Get Dispatches** → stops in route order + load manifest.
2. **Scan Load** each tote → **Depart** → print **Trip Sheet**.
3. **Deliver Stop** for Andheri (receiver name) → totes now *At Store*.

### Step 5 — Store receives (§25)

1. **Shipments in Transit** report → filter *Store Andheri - _TP* → tick the shipment → **Receive Selected** → Store Receipt.
2. **Scan Totes** (seal *Intact*) → lines checked; for a *Full Check* store use **Scan Items**. Enter one line 2 short to test discrepancies → **Submit** → stock lands in *Store Andheri*; a **Transfer Discrepancy** opens.
3. *Checker* (Warehouse Manager): **Start Investigation** → set *DC Finding* → **Submit Findings**; another approver → **Approve & Adjust**.
4. **Store Stock Overview** report → Andheri shows the received stock.

### Step 6 — Sell at the store (§26)

1. **POS Opening Entry** for the Andheri profile → open **Point of Sale**.
2. **Pharmacy Search** → type *Paracetamol* or *PAN-40* → batch (FEFO pre-selected), unit (Tablet / Strip for loose items) → **Add to Bill** → pay → submit.
3. Give a manual discount above 5% as a Store Pharmacist → submit refused → *checker* **Approve Discount** → submit.

### Step 7 — Close the loop

1. **Purchase Invoice** from the Apex PO (linked to the receipt) at a slightly higher rate → submit → *Three-Way Match = Debit Note Raised* with a draft Rate Difference debit note (§11).
2. Reports: **Supplier Performance**, **Stock by Location** (Show = Zone), **Near Expiry Stock**, **Tote Balance by Store**.

---

## 0. Before You Test

These are one-time setups that several modules depend on.

| Setup | Where | Needed for |
|---|---|---|
| Users with roles: Buyer, Purchase Manager, Category Manager, Compliance Pharmacist, Pharmacy Management, Pharmacy Accounts, Warehouse Manager, Inward QC Executive, Picker Packer, Store Pharmacist, Area Manager. Use **separate users** for maker and checker — creators can never approve their own documents | User → Roles | Approvals, maker-checker, cage custody, counts, alerts |
| Warehouse tree: one warehouse with **Warehouse Role = DC**; under it bins with **Zone Type** Receiving, General, Cold Room (2-8C), FMCG, Scheduled Drug Cage, Quarantine (Ambient and 2-8C), Returns, Expired; set **Storage Condition** and **Bin Capacity** | Warehouse | Put-away, cage, quarantine, storage rules |
| Drug Licences for your test supplier (20B/21B), DC warehouse (20B) and store (20/21) | Drug Licence | Every purchase/sale (licence check) |
| Default outgoing Email Account | Email Account | PO emails, discrepancy notes, follow-ups (otherwise status shows *Failed*) |
| Scheduler on: `bench --site pharmacy.local enable-scheduler` | Terminal | Hourly: PO acknowledgement reminders, pick-face top-ups. Daily: licence alerts, backorder follow-ups, supplier performance, near-expiry alerts |
| Buying Settings → **Maintain Same Rate Throughout Purchase Cycle** = off | Buying Settings | Three-way match rate debit notes |
| Supplier contacts added under Supplier → **Portal Users** (role Supplier) | Supplier | PO acknowledgement portal |
| Stock Settings → **Pharmacy Inventory Control**: Warehouse Manager approval limit (default ₹10,000), ABC count cycles (A 30 / B 90 / C 180 days) | Stock Settings | Adjustments, counts |
| Items' **ABC Classification** (A/B/C) | Item | Cycle counts |
| **Stock Adjustment Reason** codes — seeded on migrate (Damage, Breakage, Expiry Write-off, Recall Destruction, Theft / Loss, Found Stock, Count Variance, Data Entry Correction, Sample Issued, QA Rejection) | Stock Adjustment Reason | Adjustments |
| **Pick Face** records for fast-moving items in pick bins | Pick Face | Top-ups |
| **Pharmacy Store**: *Accept Substitutes*, *Internal Customer* (for invoiced stores), GSTIN, Store Grade, *Receiving Check* (blank = grade A/B tote level, C/D full) | Pharmacy Store | Substitution, dispatch, store receiving |
| Stock Settings: *Stores Report Receipt Discrepancies Within (Hours)* (24), *Auto-approve Patient-need Store Transfers up to* (₹5,000) | Stock Settings | Store receiving, transfers |
| **POS Profile** per store (warehouse = store, price list Standard Selling, taxes template with *Included in Print Rate* so bills are MRP-inclusive), POS Opening Entry; **POS Discount Limit** per role (seeded: Store Pharmacist 5%, Area Manager 20% + approves, Pharmacy Management 30% + approves); **Pricing Rules** for automatic discounts; **Customer Groups** for customer types | POS Profile, POS Discount Limit, Pricing Rule, Customer Group | Store billing |
| **Delivery Route**: DC, default dispatch time, stores in sequence with distance (km) — saving it sets each store's route | Delivery Route | Pick waves, trips, e-way bill distance |
| **Vehicle** (own fleet, licence plate) and **Driver** masters; transporters as Suppliers for hired vehicles | Vehicle, Driver, Supplier | Trips |
| DC warehouse **GSTIN** (Warehouse → GSTIN); Company → **Default In-Transit Warehouse** (a Transit-type warehouse) | Warehouse, Company | Challan vs invoice, transit |
| **Tote** masters: Standard, Crate, Insulated Cold Box (ice box), Scheduled Drugs; print *Tote Label*. Stock Settings → *Totes Due Back from Stores Within (Days)* (default 7) | Tote, Stock Settings | Picking, packing, tote tracking |
| GST Settings → auto-generate **e-Waybill** and **e-Invoice** (needs India Compliance API credentials) | GST Settings | e-way bill / IRN on dispatch documents |

**Demo catalogue** (already loaded on `pharmacy.local`; re-runnable, skips existing records):
`bench --site pharmacy.local execute pharmacy.demo_data.create_demo_items --kwargs '{"company": "_Test Pharmacy"}'`
25 real Indian brands with salt, strength, form, manufacturer, Tablet → Strip → Box conversions, HSN, GST template, EAN-13 test barcodes (prefix 890999), Standard Buying (PTR) and Selling (MRP) prices per pack, NPPA ceilings and ABC class:

| Use for | Items |
|---|---|
| OTC + substitutes (same salt/strength) | CALPOL-500, CROCIN-ADV-500, NIR-PCM-500 (private label), DOLO-650 |
| Schedule H / H1 | AUGMENTIN-625 (Below 25C), AZITHRAL-500, PAN-40, GLYCOMET-500, TELMA-40, ATORVA-10, ECOSPRIN-75 / ZIFI-200, LEVOFLOX-500 |
| Schedule X / NDPS (cage, register) | ADDWIZE-10 / ALPRAX-025, RIVOTRIL-05 |
| Cold chain 2-8C | HUMINSULIN-R-40 (vial), LANTUS-SOLOSTAR (pen) |
| Wellness / FMCG / Cosmetic / Surgical | REVITAL-H, ENSURE-400, DETTOL-250, CETAPHIL-GSC-125, VOLINI-30, DISPOVAN-5ML, VENUS-N95 |

Prices are indicative; barcodes are generated test codes, not the products' real EANs.

Test items: set **Regulatory Category**, **Storage Condition**, **Salt/Strength**, **ABC Classification**, HSN and a GST Item Tax Template (0/5/18%). New stock items get batch + expiry tracking automatically.

After pulling new code: `bench --site pharmacy.local migrate`, `bench build --app pharmacy`, then hard-reload the browser (Cmd+Shift+R). If the Pharmacy sidebar looks stale, run `localStorage.removeItem("sidebar_item_map")` in the browser console and reload.

---

## 1. Implementations Completed

| # | Module | What it does |
|---|---|---|
| 1 | Roles & masters | 15 pharmacy roles; item groups; Box/Strip/Tablet UOMs; GST 12%/28% templates disabled; track changes |
| 2 | Item / batch master | Salt, strength, dosage form, manufacturer, category, storage; batch `{item}-{supplier batch}`; MRP per pack; NPPA ceiling check |
| 3 | Drug licences | Licence matrix on PO/PR/PI/SI/POS/DN/transfers; daily 30/15/7-day alerts |
| 4 | Storage, shelf life, Rx | Storage condition & cage rules; bin capacity; shelf life on receipt / store dispatch; prescription at sale |
| 5 | PO approval matrix | One warehouse per PO; approvals by value and category; maker ≠ checker |
| 6 | Purchase suggestions | DC suggestions from demand, lead time, open POs, MOQ |
| 7 | Patient special orders | Patient orders tracked SO → PO → PR → store |
| 8 | Store replenishment | Schedules, order days, off-schedule indent approval |
| 9 | Purchase terms | Rate contracts (Blanket Order) with PTR + trade discount; schemes (Pricing Rule); cash discount (Payment Terms); above-contract approval |
| 10 | PO dispatch & acknowledgement | PO PDF emailed on submit; supplier portal acknowledgement; reminders |
| 11 | Fulfilment & supplier performance | Short close with reason; backorder follow-up; fill rate, lead time, on-time; report |
| 12 | Three-way match | PO vs GRN vs invoice; draft qty/rate debit notes |
| 13 | Inbound | Gate entry; Scan & Receive; receipt checks; cold chain; discrepancy notes |
| 14 | Quarantine | QA decisions; non-sellable zones blocked from allocation |
| 15 | Put-away & labels | Directed put-away by zone/condition/capacity; batch, GRN and bin labels |
| 16 | Controlled drugs | Locked cage custody; Controlled Drug Register |
| 17 | Stock by location, ageing & valuation (WH-01) | Stock by site/zone/bin/item/batch with expiry, MRP, age buckets and value |
| 18 | Bin moves & pick-face top-up (WH-02) | Pick faces with min/max; hourly FEFO top-up transfers from reserve |
| 19 | Stock counts (WH-03) | ABC cycle counts and full PV; blind handheld counting; tiered variance approval → Stock Reconciliation |
| 20 | Stock adjustments (WH-04) | Reason codes; value-tiered approval, maker ≠ checker; track changes |
| 21 | Stock holds (WH-05) | QC / Recall / Legal holds block picking, reserving, billing and moves except into holding zones |
| 22 | Expiry & movement (WH-06) | Near-expiry alerts at 180/90/60/30 days; Near Expiry and Slow & Non-Moving reports |
| 23 | DC outbound to stores | Pick waves by route from due indents; FEFO allocation respecting store shelf life, ≤2 batches/line; handheld zone picking into typed totes; short picks (backorder / substitute / cancel); seals and cold boxes; challan or tax invoice; scheduled drugs on separate documents with register entries |
| 24 | Routes & trips | Delivery Route with store sequence; Route Day preview of stores with items due; Dispatch Trip (own/hired vehicle, driver), stops in sequence, tote load manifest with scan-to-load, e-way bill transport details on departure; Trip Sheet and Load Manifest prints |
| 25 | Tote, crate & ice-box tracking | Custody by store (issued on delivery, returned on collection, missing/found, damaged); movement log; overdue alert; Tote Balance by Store report |
| 26 | Store receiving & transfers (ST-01 to ST-05) | Shipments in Transit with ETA; Store Receipt by tote scan (tote-level or full check by store, seal check, discrepancy window, auto-receive after it); Transfer Discrepancy workflow ending in approved adjustments; Store Transfer Request with approval and challan/invoice; Store Stock Overview |
| 27 | Store billing (POS-01 to POS-04) | Pharmacy Search on ERPNext POS (barcode / brand / salt, stock, FEFO batches with expiry & MRP, substitutes); FEFO default batch, expired/held/recalled batches blocked; loose strips/tablets priced from pack MRP; price list = batch MRP, never above MRP; Pricing Rule discounts + role limits with remote approval |
| 28 | Prescriptions, registers & customers (POS-05, POS-06) | Schedule H/H1/X/NDPS bills blocked without prescription file, doctor name and reg. no; patient name required for H1/X/NDPS; Schedule H1 register (and X/NDPS Sale lines) written from the bill, reversed on cancel; Customer by mobile number (unique, 10 digits); saved Customer Prescriptions (picked on the bill, auto-saved from a bill, validity date); Customer Purchase History report |
| 29 | Online orders (website backend for Frappe Builder) | Website API (catalogue, pincode, cart, coupons, loyalty, prescription upload, checkout, orders); cart = draft Sales Order, purchase = Sales Order; pharmacist prescription check with log; Schedule X / NDPS never sold online; allocation to nearest store with stock or DC, split or transfer; billing by the dispatching location (FEFO, its GSTIN address); Razorpay via Payment Request, or COD |

---

## 2. Step-by-Step UI Testing

### 1. Masters, Batches & NPPA

1. **Item** → new stock item: set Regulatory Category (e.g. Schedule H) and Storage Condition → save. *Has Batch No* and *Has Expiry Date* are ticked automatically; Rx Required is ticked for H/H1/X/NDPS.
2. Leave Regulatory Category blank → save is blocked.
3. **NPPA Ceiling Price** → add one for the item (e.g. ₹2.00 per unit). Give the item a Strip UOM (conversion 10), Sales UOM = Strip and a 5% GST template.
4. **Batch** → new batch with *Supplier Batch No* `AB1` and no Batch ID → saved as `{item}-AB1`. Set MRP ₹21.00 per Strip → saves; MRP ₹21.01 → blocked (2.00 × 10 × 1.05).
5. Check **Item Tax Template** list: 12% and 28% templates are disabled.

### 2. Drug Licences & Alerts

1. **Drug Licence** → add Form 20B for the supplier, valid to next year → status *Active*. Set Valid Upto within 30 days → *Expiring*; in the past → *Expired*.
2. Make a **Purchase Order** to a supplier with only a Form 20 (retail) licence → save is blocked (needs 20B/21B).
3. Sell a Schedule H item on a **Sales Invoice** from a DC warehouse that holds only 20B, to a customer with no licence → blocked (retail sale needs 20/21).
4. Alerts: with the scheduler on, licences expiring in exactly 30/15/7 days produce a notification and email to Compliance Pharmacist users the next morning.

### 3. Storage, Shelf Life & Prescription

1. **Shelf Life Rule** → Applies To *Regulatory Category* = Schedule H, Min Days Supplier Receipt **180**, Min Days Store Dispatch **90** (values are **days**). Where an item-group rule also applies, the stricter wins.
2. Receive a batch with 120 days to expiry on a Purchase Receipt → blocked on submit.
3. Transfer a 60-day batch from DC to a **Store** warehouse (Stock Entry, Material Transfer) → blocked. Selling the same batch at the store counter is allowed.
4. Receive a 2-8C item into an Ambient bin → blocked. Below 25C item into a 2-8C bin → allowed.
5. Set a bin's capacity to 100 with 90 in stock; receive 20 → blocked at submit.
6. **Sales Invoice / POS Invoice** with an Rx item to a walk-in customer → submit blocked until *Prescription*, *Doctor Name* and *Doctor Registration No* are filled (Prescription section).

### 4. PO Approval Matrix & One Warehouse per PO

1. **PO Approval Matrix** (`/app/po-approval-matrix`): pre-seeded rules — Schedule X / H1 lines → Compliance Pharmacist; 50K–2.5L Purchase Manager (L2); >2.5L Pharmacy Management (L3). POs below ₹50K with no Schedule X / H1 lines need **no approval** (the Buyer rule for 0–50K is disabled: buyers raise POs, they don't approve them). Rules exist for two companies, *_Test Pharmacy* and *_Test Company*.
2. **Purchase Order** with lines for two warehouses → save blocked.
3. Save a valid PO → Approvals table and **Approval Status = Pending**. Submit → blocked: *Waiting for Level 1: …*.
4. As the creator, **Approval → Approve** → refused (maker ≠ checker, administrators included).
5. Log in as the level-1 role → **Approve**; the next level is notified. **Reject** needs a reason; the creator re-saving restarts approval.
6. Change qty or rate after approval → all levels reset to Pending.

### 5. DC Purchase Suggestions

Demo data (loaded on `pharmacy.local`; re-runnable): `bench --site pharmacy.local execute pharmacy.demo_data.create_purchase_suggestion_data` — DC **Main DC - _TP** (bins: Receiving, General, General Cool, Cold Room, Cage, FMCG, Quarantine, Cold Quarantine), stores **Store Andheri / Store Bandra** served by it, suppliers Apex Pharma Distributors (3-day lead), Coldline Biologicals (5), Wellness Wholesale (7) with licences, preferred supplier / MOQ (one box) / last purchase rate on each item, DC opening stock, 60 store invoices over the last 30 days, an open online order, and a *Dolo 10+1* free-goods scheme (from 450 units).

1. **Purchase Suggestion** → Warehouse **Main DC - _TP**, Demand Period 30, As of Date today → **Save**. Expect ~13 lines; Calpol and Glycomet (well stocked) get none; Dolo shows free goods from the scheme.
2. **Generate Suggestions** → items table fills with demand, lead time, pending POs, MOQ-rounded order qty.
3. **Submit** → **Create Purchase Orders** → one draft PO per supplier for this DC, priced from the last purchase rate (contracts/schemes then apply on the PO).

### 6. Patient Special Orders

1. **Sales Order** → tick *Patient Special Order* → fill Patient Name, Phone, Store, Priority → add the item → submit.
2. On the PO / Stock Entry for the item, tick *Patient Special Order* and link the Sales Order; it is tracked through receipt and store transfer.

### 7. Store Replenishment & Indents

1. **Replenishment Schedule** → Scope (Store / Cluster / All), Applies To, Frequency and Order Days, cover days or min/max.
2. **Material Request** (transfer) for a store with off-schedule items above the store's threshold → Area Manager approval needed before submit.

### 8. Purchase Terms (Rate Contracts, Schemes, Cash Discount)

1. **Blanket Order** (Rate Contract) → Type *Purchasing*, supplier, From/To dates, Default Trade Discount 10% → line with **PTR** ₹100 → Rate becomes ₹90 → submit.
2. A second overlapping contract for the same supplier + item → blocked.
3. **Purchase Order** for that supplier + item → line shows Rate Contract, Contract Rate ₹90; price list rate 100, discount 10%.
4. Edit the rate to ₹95 → **Above Contract Rate** ticked and a level-1 *Category Manager* approval is added (Basis: *Above contract rate*).
5. **Pricing Rule** → Buying, Supplier, Product Discount, same item, Min Qty 10, Free Qty 1, Is Recursive (recurse every 10) → PO for 20 adds a free row of 2 at rate 0.
6. Cash discount: **Payment Terms Template** with Discount % and validity → set on the Supplier; appears on the PO payment schedule.

### 9. PO Email & Supplier Acknowledgement

1. Submit an approved PO → PO Email Status **Sent** (or **Failed** with reason on the timeline if email isn't set up). The email carries the PO PDF and a portal link.
2. **Supplier → Send to Supplier** resends.
3. Log in as a supplier portal user → menu **Acknowledge Purchase Orders** (`/po-acknowledgement`) → open the PO → enter Expected Delivery Date (per-line overrides optional), confirmation no, remarks → **Acknowledge**. The PO shows Order Confirmation No/Date, line Expected Delivery Dates, *Acknowledged*; the buyer is notified.
4. Buyer alternative: **Supplier → Record Acknowledgement** on the PO.
5. Unacknowledged after the hours in Buying Settings (default 24) → buyer notified and one reminder email.

### 10. Partial Supplies, Short Close & Supplier Performance

1. Receive part of a PO → PO **Supply Performance** section shows Qty/Line Fill Rate, Pending Qty, First Receipt, Lead Time.
2. Standard **Close** on a PO still awaiting goods → refused. **Status → Short Close** → pick a reason (Other needs remarks) → PO closed; reason, by and on recorded.
3. Backorders: lines past expected delivery get a buyer notification and supplier email every N days (Buying Settings, default 3).
4. **Supplier Performance** report (`/app/query-report/Supplier Performance`) → fill rates, average vs promised lead time, on-time %, short-closed count. The Supplier form shows 90-day figures (updated daily).

### 11. Three-Way Match & Debit Notes

1. **Purchase Invoice** for a stock item not linked to a Purchase Receipt (update stock off) → submit blocked: *GRN required*.
2. Invoice linked to PO + GRN at matching qty/rate → **Three-Way Match = Matched**.
3. Invoice 12 units at ₹95 where GRN accepted 10 at PO rate ₹90 → submits; status **Debit Note Raised**; lines show PO rate, GRN qty and differences; *Debit Notes Raised* lists two **draft** returns:
   - *Qty Difference*: −2 units at ₹95 (reduces billed qty on PO/GRN).
   - *Rate Difference*: −10 units at ₹5 (billed qty untouched).
4. Pharmacy Accounts users are notified to review and submit them.

### 12. Inbound: Gate Entry, Scan & Receive, Checks, Cold Chain, Discrepancy

1. **Gate Entry** → **Purchase Order** (fills supplier, company and receiving DC; only submitted POs awaiting goods are offered) → vehicle, *Supplier Invoice No* (several bills: comma-separated), *No. of Cases* → submit → status *Arrived*. Changing the supplier to one other than the PO's → refused.
2. On the submitted Gate Entry: **Create → Purchase Receipt** → a receipt built from the gate entry's PO, with the gate entry, *Supplier Delivery Note* (= supplier invoice no.) and vehicle filled in. Receipts made against a gate entry are listed on it under *Receiving*. (A receipt made from the PO picks up its gate entry on save; with no gate entry for the supplier → save blocked.)
3. **Scan & Receive** → scan barcode (or type item code) + Enter → item and open PO line shown → enter qty, free qty, invoice qty, supplier batch, mfg/expiry, MRP (+ temperature/logger for cold items) → **Add Line**; dialog stays open.
4. Save → batches created as `{item}-{supplier batch}`; free qty becomes a separate zero-rate line; each line shows **Receipt Flags**.
5. Blocked on submit: item not on PO; qty over PO pending; shelf life below rule; cold item without reading.
6. MRP different from the last batch → *MRP changed from …*; submit needs **Approve MRP Changes** by a Category Manager (not the creator).
7. Cold item with 9.5 °C (or logger *Excursion*) → line moves to the DC's 2-8C Quarantine bin. On submit a draft **Quarantine Decision** is created and QA notified.
8. Rejected qty, or received ≠ *Qty as per Supplier Invoice* → draft **Receipt Discrepancy** (Damage / Shortage / Excess). Damage lines need a photo; submit emails the note to the supplier.

### 13. Quarantine & QA Release

1. Warehouses in Quarantine / Returns / Expired zones show **Non-Sellable** (ticked automatically).
2. Sales Order, Pick List, Delivery Note, Sales Invoice (update stock), POS Invoice or Stock Reservation from such a warehouse → blocked. Pick List never allocates from them.
3. Stock Entry out of quarantine to a normal bin → blocked (*QA release required*); into Expired zone → allowed.
4. **Quarantine Decision** → Decision:
   - *Release to Stock* + Release To → submit → stock transferred.
   - *Return to Supplier* → draft purchase return of that line.
   - *Destroy* → draft Material Issue linked to the decision.

### 14. Put-away & Labels

1. Receive into a **Receiving** zone bin → on submit a **Put-away List** is created with suggested bins (Cage for X/NDPS, Cold Room for 2-8C, FMCG for FMCG/Cosmetics groups, else General; condition and free capacity respected; lines split if needed).
2. **Scan Put-away** → scan batch label, then bin label → line marked scanned (warning if not the suggested bin).
3. Submit once all lines are scanned → transfer posted, status *Completed*.
4. Labels (Print menu):
   - **Batch** → *Batch Label* (item, barcode, expiry, MRP).
   - **Purchase Receipt** → *GRN Batch Labels* (one per batch line).
   - **Warehouse** → *Bin Label* (barcode, zone, condition, capacity).

### 15. Schedule X / NDPS Cage & Register

1. Receive a Schedule X item → line routed straight to a Scheduled Drug Cage bin (*Routed to cage …*).
2. Submit the GRN as a user **without** Compliance Pharmacist → blocked. Submit as Compliance Pharmacist → OK.
3. **Controlled Drug Register** (`/app/controlled-drug-register`) → Receipt entry: date, item, batch, expiry, supplier, invoice nos, qty in, running balance. Entries can't be edited or deleted.
4. Cancel the GRN → a *Receipt Reversal* entry is added.
5. Any Stock Entry / Delivery Note into or out of the cage needs the Compliance Pharmacist role.

### 16. Stock by Location, Ageing & Valuation (WH-01)

1. **Stock by Location** report (Pharmacy → Reports) → Company, optional Warehouse/Site, Zone, Item, Category, *Expiring Within*.
2. *Show = Batch*: one row per site → zone → bin → item → batch with expiry, days to expiry, MRP, qty, valuation rate, value, age (days since first receipt), age bucket, *On Hold*.
3. *Show = Bin / Zone / Site / Item*: totals with value split into 0-30, 31-90, 91-180 and 180+ day age buckets.

### 17. Bin Moves & Pick-Face Top-up (WH-02)

1. Bin-to-bin move: **Stock Entry** → Material Transfer between bins (storage, capacity, quarantine, hold and cage rules apply).
2. **Pick Face** → Pick Bin, Item, Top Up Below 20, Fill Up To 100.
3. Bring the pick bin below 20 → within the hour a **draft** Material Transfer appears (Pick Face Top-up set), taking earliest-expiry batches from reserve bins in the same DC (never from pick faces, holding zones or held batches). Pickers and Warehouse Managers are notified; submit it after moving the stock.

### 18. Stock Counts (WH-03)

1. **Stock Count** → *Cycle Count* (optional ABC class) or *Full Physical Verification*, Warehouse/Store (a group counts every bin under it) → **Get Lines**. Cycle counts include only items whose class is due.
2. Log in as a counter (e.g. Inward QC Executive / Store Pharmacist): **System Qty** and variance are not visible (blind count).
3. **Scan Count** → scan bin → scan batch/item → qty → **Record**; unknown stock found in a bin is added as a new line.
4. Submit once every line is counted → variances calculated; status **Pending Approval** (or *Approved* if none). The Approver Role is Warehouse Manager up to the Stock Settings limit, Pharmacy Management above.
5. A counter or the creator trying **Variance → Approve** → refused. Approver → **Approve** → a Stock Reconciliation (reason *Count Variance*) is posted and linked; **Reject** needs a reason.

### 19. Stock Adjustments (WH-04)

1. **Stock Entry** Material Receipt/Issue or **Stock Reconciliation** without *Reason Code* → save blocked.
2. With a reason → Adjustment Value and Approver Role filled; submit blocked until approved.
3. The creator sees no **Approve Adjustment** button; the approver (role per value tier) approves → submit allowed. Changing lines afterwards clears the approval.
4. Exempt: opening stock; reconciliations from an approved Stock Count; QA *Destroy* issues (reason *QA Rejection*).
5. Audit: Stock Entry and Stock Reconciliation keep a version history (track changes).

### 20. Stock Holds (WH-05)

1. **Stock Hold** → Hold Type (QC / Recall / Legal), Item, optional Batch and Warehouse, reason, reference → save (status *Active*).
2. Sales Order, Pick List, Delivery Note, Sales Invoice (update stock), POS Invoice or Stock Reservation using held stock → blocked (*Stock on hold*). A batch-level hold blocks only that batch.
3. Stock Entry moving held stock into a normal bin → blocked; into a Quarantine / Returns / Expired bin → allowed.
4. **Release Hold** with remarks → status *Released*; released by/on recorded.

### 21. Near Expiry & Slow / Non-Moving (WH-06)

1. Daily job: batches reaching 180, 90, 60 or 30 days to expiry today → notification (count and value) to Warehouse Manager and Category Manager; store stock also to Store Pharmacists. Clicking opens **Near Expiry Stock**.
2. **Near Expiry Stock** report → buckets Expired / within 30, 60, 90, 180 days, by site, zone and bin.
3. **Slow and Non-Moving Stock** report → per item and warehouse: last outward, days since, outward in period, days of cover; *Non-Moving* (no outward beyond the set days) and *Slow-Moving* (cover above the set days).

### 22. DC Outbound: Pick Waves, Picking, Totes & Dispatch

1. Submit store **Material Requests** (Material Transfer) with schedule dates on or before today (from the replenishment schedules).
2. **Pick Wave** list → **Create Today's Waves** → Company + DC → one wave per active **Delivery Route** of that DC, with its stores' due indents, already allocated. Or create a wave by hand → **Plan → Get Indents** → **Allocate (FEFO)**.
3. Check the **Pick Lines**: earliest-expiry batches whose remaining life meets the store-dispatch shelf-life rule; at most 2 batches per line (Stock Settings); pick faces preferred; held, quarantine and receiving stock never used; shortages appear as *Short* lines. ❄ = cold chain, 🔒 = Schedule X / NDPS.
4. **Pick** → choose your Zone → scan bin → batch → qty → tote. A wrong bin or batch is refused. Cold-chain items go only into *Insulated Cold Box* totes, Schedule X/NDPS only into *Scheduled Drugs* totes, and a tote can't serve two stores.
5. **Pack → Resolve Short Lines**: mark a pending line short, then choose *Backorder* (stays on the indent), *Substitute* (store must accept substitutes; same salt/strength/form, not X/NDPS, MRP not higher; private label first) or *Cancel* (qty cancelled on the indent). A comment is added to the indent.
6. **Pack → Seal Tote**: seal number; cold boxes also need ice packs and the temperature at packing.
7. **Dispatch** (all lines picked or resolved, all totes sealed) → per store:
   - Same company and GSTIN → **Stock Entry** (delivery challan) into the in-transit warehouse, with destination store and totes/seals.
   - Different GSTIN or company → **Sales Invoice** to the store's internal customer (update stock, target warehouse = store) → IRN and e-way bill via India Compliance.
   - Schedule X / NDPS lines go on a **separate** document; Controlled Drug Register gets *Transfer* entries; print **Scheduled Drug Dispatch Note**. Submitting it needs the Compliance Pharmacist role (cage custody).
8. Totes show *Dispatched* with the document; Store Pharmacists are notified, including any short lines and their outcome.

### 23. Routes & Trip Planning

1. **Delivery Route** → stores with sequence 1, 2, 3…, distance and minutes from DC → save. Each Pharmacy Store's *Route* is updated. A store already on another active route → blocked.
2. **Route Day** → pick a date → stores with items due that day, in sequence (each store is served on every day it has items due).
3. After a wave is dispatched: **Dispatch Trip** → date, route, *Own* vehicle (Vehicle → vehicle no. filled) or *Hired* (transporter, vehicle no., hire charges), driver → **Get Dispatches** → stops in route sequence with documents, totes, ice boxes, scheduled totes; the **Load Manifest** lists every tote with seal and document.
4. **Scan Load** at the dock: each tote marked loaded; an unknown tote is refused. **Depart** is refused until all are loaded; it writes vehicle no., transporter, distance and LR no. (trip) onto every challan / invoice for the e-way bill, and totes become *In Transit*.
5. Print **Trip Sheet** (stops, totes, ❄ ice boxes, 🔒 scheduled, signatures) and **Load Manifest** (totes by store).
6. **Deliver Stop** with the receiver's name → stop *Delivered*; **Complete Trip** once every stop is delivered.

### 24. Tote, Crate & Ice-Box Tracking

1. On **Deliver Stop**, that store's totes become *At Store* (Held by Store, Issued On) and a *Tote Movement* "Issued" is logged.
2. **Collect Empties** on the trip → condition Good/Damaged → scan → tote *Available* again (or *Damaged*), movement "Returned" from that store.
3. On a Tote: **Mark Missing** (with remarks) / **Mark Found**; a missing tote scanned on a later trip is logged Found + Returned.
4. **Tote Balance by Store** report → per store and type: issued, returned, returned damaged, held now, overdue, missing.
5. Daily: totes held longer than the return period → notification to Dispatch Coordinator and Warehouse Manager.

### 25. Store Receiving & Transfers (ST-01 to ST-05)

1. **ST-01** — **Shipments in Transit** report (filter Store): every challan/invoice not yet received, with status *At DC / On Trip / Delivered*, trip, vehicle, driver, totes and **Expected Arrival** (trip departure, or route dispatch time, + the store's minutes from DC).
2. **ST-02** — tick a shipment → **Receive Selected** → a **Store Receipt** with the shipment's lines and totes; *Check Level* from the store (tote level or full); *Report Discrepancies By* = delivery time + 24 h.
   - **Scan Totes** with seal Intact → that tote's lines count as received (tote level). Seal *Broken* → its lines need a full count. Ice-box and Schedule X/NDPS lines always need a full count.
   - **Scan Items** → batch/item, qty received, of which damaged.
   - Submit → stock moves from transit into the store (end-transit Stock Entry, linked); for another company's store a **draft inter-company Purchase Invoice** is created. After the window, differences can no longer be reported.
   - Hourly: shipments delivered more than 24 h ago without a receipt are **auto-received** as dispatched.
3. **ST-03** — differences open a **Transfer Discrepancy** (Short / Excess / Damaged lines, photos, store remarks); Warehouse Managers are notified.
   - Warehouse Manager → **Start Investigation** → set a *DC Finding* per line (Found at DC, Transit Loss, Excess Confirmed, Damaged Write-off, Not Accepted) → **Submit Findings** → approver role by value (Stock Settings limit).
   - Someone other than the investigator/reporter → **Approve & Adjust** → stock entries posted and linked per line (transit → DC, transit loss write-off, DC → store, damage write-off, or transit → store) → *Resolved*; stores notified. **Send Back** returns it to the warehouse.
4. **ST-04** — **Store Transfer Request**: from / to store, purpose *Patient Need* (patient, phone, prescription) or *Stock Balancing*, items (available qty and value shown) → **Request Approval**. Patient need up to ₹5,000 is approved at once; otherwise an Area Manager (not the requester) approves or rejects. **Dispatch** → earliest-expiry batches at the sending store → challan (same GSTIN) or tax invoice (different GSTIN/company); Schedule X/NDPS lines write register entries. The receiving store sees it in Shipments in Transit and receives it with a Store Receipt.
5. **ST-05** — **Store Stock Overview** report: per store and item — on hand, value, in transit, pending indent qty, sold in period, average daily sales, days of cover; live from the same stock ledger stores bill against.

### 26. Store Billing (POS-01 to POS-04)

**POS demo data** (loaded on `pharmacy.local`; re-runnable): `bench --site pharmacy.local execute pharmacy.demo_data.create_pos_test_data`

| What | Detail |
|---|---|
| POS Profiles | *Store Andheri POS* (default for Administrator), *Store Bandra POS*; price list Standard Selling; tax template *Output GST In-state (MRP Inclusive)*; Cash; POS Opening Entry open for Andheri with ₹500 float |
| Store Andheri stock | Two batches for DOLO-650 (A1 expires in 75 days, A2 in 420), PAN-40 (A1 90 days, A2 540), AZITHRAL-500 (**RC = recalled**, A2), GLYCOMET-500 (**EX = expired 5 days ago**, A2); one batch of CALPOL-500, CROCIN-ADV-500, NIR-PCM-500, AUGMENTIN-625, ALPRAX-025, ENSURE-400, CETAPHIL-GSC-125, VOLINI-30, DETTOL-250. Stores hold ambient and below-25°C items only (no insulin) |
| Stock Hold | *Recall* on batch AZITHRAL-500-RC |
| Customers | *Walk-in Customer* (Individual), *Mr. R. Iyer* (Senior Citizen), *Pharmacy Staff Member* (Staff) |
| Pricing Rules (higher priority wins) | Own Label 15% (Private Label group, 4), OTC Week 10% (OTC group, 14 days, 3), Staff 10% (2), Senior Citizen 5% (1) |
| Sample bills (submitted) | Walk-in: Dolo 1 strip + 5 tablets, Calpol 2 strips → OTC 10%; Mr. R. Iyer: Pan 40, Glycomet ×2, Nirmal PCM → senior 5% / own-label 15%, with prescription; Walk-in: Alprax (NDPS, with prescription) + Volini |

What the sample bills show (open them under Sales Invoice, POS):

- **FEFO**: Dolo and Pan took batch **A1** (earliest expiry); Glycomet skipped the **expired EX** batch and took **A2**.
- **Loose sale**: Dolo per *Tablet* at ₹2.24 = ₹33.60 strip MRP ÷ 15.
- **MRP as price**: *Price List Rate* = batch MRP for the unit; *Pricing Rule Discount* shows the automatic % (10% OTC, 5% senior, 15% own label; none on Alprax).
- **Rx**: bills with Schedule H / NDPS items needed prescription and doctor details.

Things to try at the counter with this data:

- Search *Azithromycin* → only batch A2 is offered; forcing AZITHRAL-500-RC on a bill → refused (*on recall hold*).
- Add GLYCOMET-500-EX by hand → refused (*expired*).
- Sell ALPRAX-025 by *Tablet* → refused (not a loose-sale item).
- As a Store Pharmacist, give 8% extra discount on Calpol → *Discount Approval = Pending*, submit refused → Area Manager approves → submit.
- Bill Mr. R. Iyer for an OTC item → OTC Week 10% wins over senior 5% (higher priority).

1. Open **Point of Sale** (`/app/point-of-sale`) with the store's POS Profile → **Pharmacy Search** button (or Ctrl+K).
2. **POS-01** — scan a barcode, or type a brand (e.g. *Calpol*) or a salt (e.g. *Paracetamol*) → each match shows stock here, Rx/category, salt & strength, sellable batches (earliest expiry first, marked FEFO) with expiry, days left, MRP and stock, plus same-salt substitutes (click to search them).
3. **POS-02** — the FEFO batch is pre-selected; pick another radio to choose a different batch → **Add to Bill**. Adding an item without a batch on any screen gets the FEFO batch on save. Billing an expired batch, or one under a QC / Recall / Legal **Stock Hold**, is refused.
4. **POS-03** — for loose-sale items (e.g. DOLO-650) choose *Tablet* or *Strip*; price = batch pack MRP ÷ units per pack × units sold (*MRP for this Unit* on the line). Non-loose items (e.g. ALPRAX-025, insulin) can only be sold per their MRP pack.
5. **POS-04** — the line's price list rate is the batch MRP for the unit (tax-inclusive profile); a rate above MRP is refused.
   - Automatic discounts: **Pricing Rule** on item / item group (incl. Schedule H, OTC…) / customer group / validity dates → shown as *Pricing Rule Discount*.
   - Manual discount within the user's role limit → bills normally. Above it → *Discount Approval = Pending*; submit is refused; approvers (roles with *Can Approve*, limit ≥ requested) are notified → **Approve Discount** on the bill (not the creator) → the cashier submits. Changing qty/discount after approval asks again.

---

### 27. Prescriptions, Schedule H1 Register & Customers (POS-05, POS-06)

**Setup:** H1 items: *LEVOFLOX-500*, *ZIFI-200*; Schedule X: *ADDWIZE-10*; NDPS: *ALPRAX-025*, *RIVOTRIL-05*. Store Andheri needs stock of one of them (receive some first).

1. **Customer by mobile** → Customer *Mr. R. Iyer* → *Mobile* `+91 98200 12345` → saves as `9820012345`. Another customer with the same number → *"Mobile 9820012345 already belongs to customer …"*. Customer list → filter *Mobile*.
2. **Sale blocked without prescription** → POS / Sales Invoice at Store Andheri, customer *Mr. R. Iyer*, *ZIFI-200* → Submit → *"Prescription, Doctor Name, and Doctor Registration No are required for Rx items: ZIFI-200"*.
3. **Patient required for the register** → fill *Prescription* (attach photo/scan), *Doctor Name*, *Doctor Registration No*; with the walk-in customer and no *Patient Name* → *"Patient Name is required for the register"*. (A named customer is used as the patient automatically.)
4. **Submit** → *Saved Prescription* fills with a new **Customer Prescription** (RX-…) holding the file, doctor, patient and validity (180 days).
5. **Schedule H1 register** → Pharmacy → Reports → **Schedule H1 Register** → line: date, bill, patient, address, prescriber, reg. no, drug, batch, expiry, qty, store, prescription. Schedule X / NDPS bills write *Sale* lines in **Controlled Drug Register** with a running balance.
6. **Cancel the bill** → register gets a *Sale Reversal* line (the original stays).
7. **Repeat customer** → new bill for *Mr. R. Iyer* → *Saved Prescription* lists only his valid prescriptions → pick one → prescription, doctor and patient fill in. Expired one → *"Prescription … expired on …; capture a new one"*.
8. **History** → Customer form → **Pharmacy → Purchase History** (bills, items, batches, prescription) / **Prescriptions** / **New Prescription**. Or report **Customer Purchase History** → filter *Mobile*.

---

### 28. Online Orders (website backend)

**Setup (done):** `bench --site pharmacy.local execute pharmacy.demo_data.create_online_order_data` set up Online Order Settings, store pincodes (Andheri 400053/400058, Bandra 400050/400052, both 400049; the DC ships everywhere in 48 h), store billing addresses, a ₹40 delivery charge (free above ₹500), COD up to ₹5,000, coupon **WELCOME10** and the loyalty programme *Pharmacy Rewards*.
**Online payment:** open **Razorpay Settings**, enter your Razorpay **test** keys and save. Then make a **Payment Gateway Account** (gateway Razorpay, currency INR, a bank or clearing account) and pick it in **Online Order Settings → Payment Gateway Account**. Until then only COD can be chosen.

**Order life (Sales Order → Online Order tab → Online Status):** Cart (draft Sales Order) → Prescription Review (Rx items) → Awaiting Payment (online) → Confirmed → Partly Dispatched / Dispatched → Delivered. A rejected prescription ends in *Rejected*; the customer can cancel before confirmation.

1. **Catalogue (guest):** `/api/method/pharmacy.online.catalog.search?query=paracetamol&pincode=400053` returns Calpol, Crocin, Dolo and Nirmal PCM, with MRP, offer price and stock. `query=alprax` returns nothing (NDPS is never sold online). `get_product?item_code=DOLO-650` gives the product page with substitutes. `check_pincode?pincode=400053` gives Express 2hr, COD and the pickup stores.
2. **Cart (logged-in website user):** `add_to_cart` Dolo 650 ×2 and Augmentin 625 ×1. This creates a draft **Sales Order** with *Online Order* ticked and status *Cart*. `add_to_cart` Alprax → *"… is a NDPS drug and is sold only at the store against a prescription"*. `apply_coupon` WELCOME10 → 10% off. `set_delivery` Home Delivery with an address in 400053 → delivery charge ₹40.
3. **Prescription:** upload the file with `/api/method/upload_file` (logged in), then `attach_prescription(file_url=…)`. `place_order("Cash on Delivery")` → status *Prescription Review*; Online Order Pharmacists get a notification.
4. **Pharmacist check (desk):** open the Sales Order → **Prescription → View Prescription**, then **Approve**: enter doctor name, registration no and patient. This logs the check (who and when) in *Check Log*, saves a *Customer Prescription* and releases the order. **Reject** needs a reason, which the customer sees, and ends the order.
5. **Allocation (automatic on release / payment):** lines move to the nearest location with stock (*Locations* table). Example: Dettol ×55 with only 12 at Andheri. **Split** (default) bills 12 from Andheri and 43 from DC FMCG. **Transfer to One Location** keeps all of it at Andheri and raises a Material Request DC → Andheri for 43. A **Store Pickup** order always stays at the pickup store, with a transfer for anything short. The order reserves stock on submit, so other channels can't sell it.
6. **Bill by the dispatching location:** Sales Order → **Bill → Store Andheri**. This makes a Sales Invoice for that location's lines only, with stock update, earliest-expiry batches, never above batch MRP, the store's GSTIN address, and prescription and patient from the order. Submit it: the H1 register is filled for H1 items, and the location shows *Billed* (or *Ready for Pickup*).
7. **Delivery:** **Delivery → {store}: Out for Delivery**, then **Delivered** (for COD, enter the cash collected; a Payment Entry is posted against the invoice). When every location is delivered → *Delivered*, payment *COD Collected*.
8. **Online payment (once Razorpay is set up):** `place_order("Online")` → after the pharmacist check (if any) the order is allocated and submitted, and a Payment Request is made → `pharmacy.online.payment.get_payment_url` gives the Razorpay checkout link. Once paid, a Payment Entry is posted against the Sales Order (as an advance), the order goes to *Confirmed*, and the invoices pick up the advance automatically.

**API for the Builder pages** (`/api/method/<path>`; guest = no login needed):

| Path | Guest | Arguments | Returns |
|---|---|---|---|
| `pharmacy.online.catalog.search` | ✓ | query, pincode? | product cards: item_code, item_name, brand, generic, strength, image, pack, mrp, price, discount_pct, offers, rx_required, in_stock |
| `pharmacy.online.catalog.get_product` | ✓ | item_code, pincode? | card + description, marketer, storage, substitutes[], delivery |
| `pharmacy.online.catalog.check_pincode` | ✓ | pincode | serviceable, delivery_type, expected_by, cod_available, delivery_charge, free_delivery_above, pickup_stores[] |
| `pharmacy.online.cart.set_profile` | | full_name?, mobile? | customer |
| `pharmacy.online.cart.get_cart` | | — | cart (items, totals, payable, cod_available, rx_required …) |
| `pharmacy.online.cart.add_to_cart` / `update_cart` | | item_code, qty (0 removes) | cart |
| `pharmacy.online.cart.apply_coupon` | | coupon_code (empty removes) | cart |
| `pharmacy.online.cart.get_loyalty` / `use_loyalty_points` | | points | balance / cart |
| `pharmacy.online.cart.get_addresses` | | — | saved addresses |
| `pharmacy.online.cart.set_delivery` | | fulfilment_type (Home Delivery / Store Pickup), pincode?, pickup_store?, address (name or {address_line1, city, state, pincode, phone}) | cart |
| `pharmacy.online.cart.get_prescriptions` | | — | valid saved prescriptions |
| `pharmacy.online.cart.attach_prescription` | | file_url (from upload_file) or customer_prescription, patient_name? | cart |
| `pharmacy.online.cart.place_order` | | payment_method (Online / Cash on Delivery) | order |
| `pharmacy.online.payment.get_payment_url` | | sales_order | Razorpay checkout URL |
| `pharmacy.online.cart.my_orders` / `get_order_details` / `cancel_order` | | name, reason? | orders / order with status, payment, locations |

### §28 — Pharmacy Store Online Order, Dedicated Cart & Customer Orders with Razorpay

* **Catalog Page Route**: `/order` ([`http://localhost:8001/order`](http://localhost:8001/order))
* **Dedicated Cart & Checkout Route**: `/cart` ([`http://localhost:8001/cart`](http://localhost:8001/cart))
* **Customer Orders & Invoices Route**: `/orders` ([`http://localhost:8001/orders`](http://localhost:8001/orders))
* **Builder Designer**: `/builder` ([`http://localhost:8001/builder`](http://localhost:8001/builder))
* **Branding**: **Pharmacy Store**

#### 1. Streamlined Catalog (`/order`):
1. **Clinical Department Navigation**: Filter pills with live item counters (*All Items*, *Prescription (Rx & Schedule H)*, *OTC Healthcare*, *Cold Chain (2-8°C)*, *Surgical & Devices*, *Wellness & Nutrition*, *Controlled (NDPS/X)*).
2. **Dosage Form Chips**: Filter by *Tablets*, *Injections*, *Gels*, *Capsules*, *Devices*.
3. **View Modes**:
   - **Sections View**: Grouped by clinical departments with headers and descriptions.
   - **Grid View**: Clean multi-column product card grid.
   - **Table View**: Formulary table with medicine, salt, form, category, storage, and price.
4. **Essential Details Only on Medicine Cards**:
   - Shows **only essential clinical information**: Medicine Name, Active Generic Salt, Strength pill (`500 mg`), Packaging/UOM tag (`Tablet`), and Regulatory status (`Rx` / `OTC`).
   - Clean, uncluttered layout eliminating redundant boxes and duplicate text.
   - Refrigerated indicator (`❄️ 2-8°C`) displayed only when temperature control is strictly required.
   - Interactive in-card stepper: `[+ Add]` toggles to `[-] N in Cart [+]` upon selection.
5. **Cart Synchronization**:
   - Cart data syncs seamlessly via `localStorage`.
   - Top navbar button: `🛒 View Cart (N)` linking to `/cart` and `📋 My Orders` linking to `/orders`.
   - Floating sticky banner: `🛍️ N items in your cart (₹XXX) — [Proceed to Cart & Checkout →]`.

#### 2. Dedicated Cart & Razorpay Checkout (`/cart`):
1. **Cart Review Table**: Structured line items with active salt composition, unit price, quantity steppers, item totals, and remove button.
2. **Patient & Delivery Details**:
   - Patient Name, Phone number, and **Email Address** for tracking & invoices.
   - Fulfillment Toggle: **Home Delivery** (with pincode) or **Store Pickup** (linked retail store selector).
   - **Patient Special Order** checkbox for unstocked or priority emergency medicines.
   - Doctor prescription file upload for Schedule H / Rx drugs.
3. **Payment Methods & Automatic Sales Invoice Creation**:
   - 💳 **Razorpay Secure Gateway** (Cards, UPI, Netbanking, Wallets):
     - Powered by Razorpay Checkout SDK (`checkout.js`).
     - Submits order to ERPNext as Sales Order (`Awaiting Payment`).
     - Opens Razorpay payment modal with customer details, order amount, and theme color.
     - **On Payment Authorization**: Backend validates payment via `verify_razorpay_payment`:
       1. Submits the `Sales Order` (transitions docstatus to 1).
       2. **Automatically creates and submits the official GST `Sales Invoice`** (linked to order).
       3. **Posts and submits a `Payment Entry`**, marking the invoice status as **`Paid`** in full with zero outstanding balance.
       4. Updates `nir_payment_status = "Paid"` and `nir_online_status = "Confirmed"`.
       5. Dispatches branded order confirmation and tax invoice email to customer.
       6. Displays order confirmation screen with both Sales Order ID and Sales Invoice ID, plus direct link to `/orders`.
   - 💵 **Cash on Delivery (COD)**:
     - Places Sales Order immediately with status `Confirmed` and dispatches confirmation email.

#### 3. Customer Orders & Invoices Web Page (`/orders`):
1. **Contact Search & Auto-Load**:
   - Customers can enter their **Mobile Number**, **Email Address**, or **Order ID** (`#SAL-ORD-...`).
   - Automatically detects and loads past orders from `localStorage` if customer previously placed an order on `/cart`.
2. **Filter Status Tabs**:
   - Quick tabs for *All Orders*, *Confirmed*, *Awaiting Payment*, *Rx Review*, *Dispatched*, and *Delivered* with real-time counters.
3. **Interactive Order Cards**:
   - Card header displays Order ID, placement date, fulfillment type (`🛵 Home Delivery` / `🏬 Store Pickup`), and live status pill.
   - **Sales Invoice Callout**: If paid/invoiced, displays an emerald callout showing invoice reference (`#SINV-26-XXXXX`), status `PAID`, and a **`[ 🖨️ View & Print Tax Invoice ]`** button.
   - **Pay Now Action**: If order is in `Awaiting Payment` status, displays an amber callout with **`[ 💳 Pay with Razorpay ]`** button to complete payment directly.
   - Detailed medicine items table showing Name, Active Salt, Strength, Form, Qty, Rate, and Line Total.
   - Footer summary showing Patient Details, Payment Method, and Grand Total.
4. **Official Tax Invoice Modal & Print View**:
   - Clicking `View & Print Tax Invoice` opens a compliant tax receipt popup formatted under Drugs & Cosmetics Act and GST rules.
   - Features Pharmacy Store company header, GSTIN, Drug Licences (Form 20 & 21), billed patient details, itemized batches, tax breakdown, and a 1-click **`Print / Save PDF`** button (`window.print()`).

#### 3. Complete Post-Order Fulfillment, Picking & Delivery Workflow

```
   1. [SALES ORDER CREATED]
      (From /order or /cart with contact email)
             │
             ├─────────────────────────────────────────┐
             │ (If Rx required)                        │ (If OTC / Non-Rx)
             ▼                                         ▼
   [PRESCRIPTION REVIEW]                           [CONFIRMED]
   Online Order Pharmacist inspects doctor Rx          │
   Click "Prescription → Approve"                      │
             │                                         │
             └───────────────────┬─────────────────────┘
                                 │
                                 ▼
                     [BATCH PICKING & INVOICING]
                     In Sales Order, click "Bill → {Store}"
                     • Automated FEFO batch allocation
                     • Strict MRP ceiling enforcement
                     • Creates draft Sales Invoice (Update Stock = 1)
                                 │
                                 ▼
                     [SUBMIT SALES INVOICE]
                     • Real-time stock deducted from store/DC bins
                     • Statutory Controlled Drug Register updated
                                 │
             ┌───────────────────┴───────────────────┐
             │                                       │
     HOME DELIVERY                             STORE PICKUP
             │                                       │
             ▼                                       ▼
     Fulfillment Status:                     Fulfillment Status:
          "Billed"                           "Ready for Pickup"
             │                                       │
             ▼                                       ▼
     Click "Delivery → Out for Delivery"     Patient arrives at counter
     (Rider dispatched with cold-chain box)  Click "Delivery → Picked Up"
             │                                       │
             ▼                                       │
     Rider delivers to doorstep                      │
     Click "Delivery → Delivered"                    │
             │                                       │
             └───────────────────┬───────────────────┘
                                 │
                                 ▼
                     [PAYMENT RECONCILIATION & CLOSURE]
                     • If COD: Prompt asks "Cash Collected: ₹XXX"
                       System automatically posts submitted Payment Entry!
                     • If Razorpay: Order completes automatically
                     • Final branded "Order Delivered" email sent to customer
```

##### Step-by-Step Desk Testing Guide:

1. **Locate the Placed Order**:
   - Open **Desk → Selling → Sales Order** ([`http://localhost:8001/app/sales-order`](http://localhost:8001/app/sales-order)).
   - Filter by `Online Order = 1` or sort by latest date. Open the Sales Order (e.g. `SAL-ORD-2026-00005`).

2. **Step 1: Clinical Prescription Review** *(For Rx / Schedule H/H1 Items)*:
   - If the order contains prescription drugs, top status badge displays **`Prescription Review`**.
   - **Who Approves**: **Online Order Pharmacist** (Role: `Online Order Pharmacist`).
   - Click top toolbar button **`Prescription → View Prescription`** to inspect the customer's uploaded file.
   - Click **`Prescription → Approve`**:
     * Modal dialog opens with Doctor Name, Doctor Registration Number, and Patient Name.
     * Click **Approve and Release**:
       - Automatically creates a statutory **`Customer Prescription`** record.
       - Releases order status from `Prescription Review` to **`Confirmed`**.
       - Customer receives an automated email: *"Your prescription has been verified and your order is Confirmed"*.
   - *(If rejected, click **`Prescription → Reject`** with documented reason; notifies the customer and cancels the order).*

3. **Step 2: Automated FEFO Batch Picking & Invoicing ("Bill" Action)**:
   - When status is `Confirmed`, look at the top toolbar for the **`Bill`** button.
   - Click **`Bill → {Store Name}`** (e.g., *Bill → Andheri Retail Store*).
   - **What happens behind the scenes**:
     * **FEFO Algorithm (`pick_batch`)**: Automatically scans the store’s inventory and picks earliest-expiry batches matching the store's shelf-life rules.
     * **Price Capping**: Ensures the rate billed never exceeds the batch MRP.
     * Creates and opens a draft **`Sales Invoice`** with `Update Stock = 1` and the store's legal GSTIN address.
   - Review the invoice lines and click **Submit**:
     * Stock is deducted immediately from the physical inventory bins.
     * If Schedule H1 or Schedule X medicines are included, the statutory **`Controlled Drug Register`** entry is written in real time.
     * If **Store Pickup**: Fulfillment status transitions to **`Ready for Pickup`**.
     * If **Home Delivery**: Fulfillment status transitions to **`Billed`**.

4. **Step 3: Delivery Dispatch & Doorstep Handover ("Delivery" Actions)**:
   - Return to the **Sales Order**. Notice the dynamic **`Delivery`** dropdown button has appeared in the toolbar:
   - **For Home Delivery**:
     1. When handed to the courier/rider: Click **`Delivery → {Store}: Out for Delivery`**.
        - Status changes to **`Dispatched`**.
        - Customer receives an automated email: *"Your order is Out for Delivery"*.
     2. When the rider reaches the customer: Click **`Delivery → {Store}: Delivered`**.
        - **Cash on Delivery (COD)**: A prompt modal appears asking for **Cash Collected (₹XXX)**.
          - Enter the collected cash/UPI amount.
          - The system **automatically creates, populates, and submits a `Payment Entry`** against the Sales Invoice, clearing the customer's ledger!
          - Payment status updates to **`COD Collected`**.
        - **Razorpay Pre-paid**: Directly transitions to **`Delivered`** (payment was already reconciled upon checkout).
   - **For Store Pickup**:
     1. Invoice submission sets the order to **`Ready for Pickup`**.
     2. Customer arrives at the counter and collects their order.
     3. Pharmacist clicks **`Delivery → {Store}: Picked Up`**.
     4. If COD, enter collected cash → system generates `Payment Entry`.
     5. Status changes to **`Delivered`**.

5. **Step 4: Customer Email Notification Verification**:
   - Open **Desk → Email Queue** ([`http://localhost:8001/app/email-queue`](http://localhost:8001/app/email-queue)).
   - Verify that automated branded HTML emails were queued for:
     * `Order Placed` / `Payment Received (Confirmed)`
     * `Out for Delivery` / `Ready for Pickup`
     * `Order Delivered`
   - Check the **Sales Order Activity Timeline** (bottom of the document) to view audit timestamps for all dispatched emails and Razorpay transactions.

---

### 29. Online Order Dispatch & Delivery by Delivery Trip

**Statuses (Sales Order → Online Order tab → Online Status)** follow ERPNext **Delivery Trip** (Stock → Delivery Trip):

| Event | Online Status | Customer email |
|---|---|---|
| Delivery Note submitted (home delivery) | unchanged (*Confirmed*) | — |
| Delivery Trip with that Delivery Note **submitted** | **Dispatched** (*Partly Dispatched* if the order is not fully shipped) | "out for delivery" |
| Trip stop ticked **Visited** (trip *In Transit* / *Completed*) | **Delivered** | "delivered" |
| Delivery Trip cancelled | back to **Confirmed** | — |
| Store pickup: Delivery Note submitted | **Delivered** (no trip) | "delivered" |

1. **Address:** on `/cart` (Home Delivery) the customer fills Address Title, Address Type (Shipping / Billing), Address Line 1 and 2, Postal Code, City, State, optional GSTIN / UIN and *Save as my preferred address*. Typing the postal code fills City and State and shows whether we deliver there. On order it is saved as an **Address linked to the customer**. GST Category is *Registered Regular* with a GSTIN (the GSTIN is also set on the customer for a B2B invoice), else *Unregistered*. It is set on the Sales Order as shipping and billing address and becomes the customer's primary address. An identical address is reused, not duplicated. A Delivery Trip stop needs an address; for older web orders with no address, add one to the Delivery Note (*Shipping Address*) first.
   **Prescription:** on `/cart` attach a PDF, JPG or PNG (max 5 MB). It is uploaded as a **private** file when the order is placed (wrong type, a fake file or an oversize file is refused), linked on the Sales Order (*Prescription*) and attached to it. Pharmacists open it from Sales Order → **Prescription → View Prescription**; the public can't download it.
2. Sales Order → **Create → Delivery Note** → Submit → status stays *Confirmed*.
3. **Delivery Trip → New**: Company, Departure Time, **Driver** (required), **Vehicle**. In Delivery Stops pick the **Delivery Note**. Customer, Address and contact fill in automatically: first the Delivery Note's shipping / billing address, else the customer's shipping address, then primary, then any saved address. They are filled again on save. With no address anywhere → *"Row #1: … has no delivery address"*. Save → **Submit** → the Sales Order shows **Dispatched**.
4. On the submitted trip click **Mark Delivered → #1 {customer} · {Delivery Note}** (or tick the *Visited* column → **Update**) → Sales Order shows **Delivered**.
5. Cancel the trip → Sales Order back to **Confirmed**.
6. **Delivery Rider:** link the rider's login on the **Driver** record (*User* field). A user whose only delivery role is *Delivery Rider* sees, at `/app/delivery-trip`, only **submitted** trips where they are the driver, plus those trips' Delivery Notes, customers and addresses. They click **Mark Delivered → #stop** (or tick the *Visited* column and **Update**), but can't create, submit, cancel or change vehicle, driver or stops. Users with Delivery User / Stock User etc. still see all trips.

---

### 30. Online Order Pick & Pack (Pick List)

**Statuses:** Confirmed → **Picking** (Pick List saved as draft) → **Packed** (Pick List submitted) → Dispatched → Delivered. Cancelling or deleting the Pick List puts the order back to *Confirmed*. The customer is emailed when the order is *Packed*.

1. Online Sales Order from the DC (e.g. one with warehouse *Main DC - _TP*) → **Create → Delivery Note** → Save → blocked: *"Online order lines from the warehouse must be picked and packed first …"*.
2. Sales Order → **Create → Pick List** → Save. Locations show earliest-expiry batches and DC bins (e.g. *DC General Cool*, *DC General A1*) → order **Picking**.
3. Picker (role **Picker Packer**, now with Pick List create / submit and Sales Order read) enters **Picked Qty (in stock units)** per line. Submit without **Bag / Box Label** → *"Scan or enter the Bag / Box Label before submitting the pick"*.
4. Enter the label (e.g. `BAG-0001`) → **Submit** → *Packed By* / *Packed On* filled; order **Packed**.
5. Pick List → **Create → Delivery Note** → lines carry the Pick List → Submit → Delivery Trip (§29).
6. Store orders: the Pick List is optional; a Delivery Note straight from the Sales Order is allowed.

---

## 3. Known Gaps

- Controlled Drug Register records receipts only; sales, transfers and destruction come with outbound.
- Bin capacity counts stock units across items (no volume).
- GS1 DataMatrix barcodes are not decoded (item lookup only).
- Supplier Scheme overlaps Pricing Rule schemes; configure each scheme in one place.
- Debit notes are drafts by design; Accounts submits them.
- Count variances on cage bins need a Compliance Pharmacist to approve (the reconciliation moves cage stock).
- Expiry alerts go to every user with the role; they are not yet filtered to a user's own store.
- Store-to-store transfers have no trip/ETA unless put on a Dispatch Trip; they are received when they arrive.
- Controlled-drug register entries are not written for discrepancy adjustments (only for dispatch transfers), nor yet for retail sales of Schedule X / NDPS at stores.
- POS pricing assumes MRP is tax-inclusive; with an exclusive tax template the list price is MRP less GST so the final price still equals MRP.
- e-way bill transport details are written on departure; generating or updating Part B is done from the document via India Compliance.
- Invoiced transfers to another company need the purchase side created at the store company (inter-company purchase).
- e-way bill / IRN generation depends on India Compliance GST settings and live API credentials; nothing is generated in this app's code.
