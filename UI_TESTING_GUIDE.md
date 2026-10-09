# Pharmacy System — Implementation Overview

One system runs the whole chain: buying from suppliers, the central warehouse (DC), delivery to stores, store billing and online orders. Every step is checked against drug laws and approved by the right person. The person who creates a record can never approve it.

```
SUPPLIER ──▶ WAREHOUSE (DC) ──▶ DELIVERY TRIP ──▶ STORE ──▶ PATIENT
                 ▲                                  │
                 └────── store sales = demand ──────┘
WEBSITE ORDER ──▶ pay (Razorpay / COD) ──▶ store or DC ships ──▶ PATIENT
```

**Built on:** ERPNext 16 with India Compliance (GST, e-invoice, e-way bill) · Frappe Builder for the website · Razorpay for online payment.

---

## 1. Business Flows

### Flow 1 — Buying and stocking the stores

| # | Step | What happens | Who |
|---|---|---|---|
| 1 | Plan | System suggests what to buy from store sales, online orders, stock, open orders, lead time and minimum order quantity | Buyer |
| 2 | Order | One purchase order per supplier, priced from the rate contract, schemes (e.g. 10+1) applied | Buyer |
| 3 | Approve | By value and category; Schedule X / narcotics always need the Compliance Pharmacist | Approvers |
| 4 | Send | Order emailed as PDF; supplier confirms delivery date on the portal; late / short supplies followed up | Automatic |
| 5 | Gate entry | Vehicle, supplier invoice no. and cases recorded on arrival | Inward QC |
| 6 | Receive & check | Scan batch, expiry, MRP, free qty. Blocked: not on order, excess, short expiry, MRP above NPPA ceiling. Cold items need a temperature reading; a breach goes to quarantine | Inward QC |
| 7 | Discrepancy | Damage / shortage / excess recorded with photos; note sent to supplier | Inward QC |
| 8 | Put-away | System picks the shelf by zone, temperature and space; Schedule X / narcotics go to the locked cage | Warehouse staff |
| 9 | Supplier bill | Order, receipt and bill matched; rate or qty differences raise a debit note | Accounts |
| 10 | Store orders | Stores order on their schedule days; extra orders need approval | Store Pharmacist / Area Manager |
| 11 | Pick & pack | Grouped by route; earliest-expiry stock into sealed totes, ice boxes for cold items | Picker / Packer |
| 12 | Dispatch | Delivery challan or tax invoice with e-way bill; vehicle, driver, load manifest, trip sheet | Dispatch Coordinator |
| 13 | Store receives | Scan totes, check seals; differences within 24 h investigated and settled | Store Pharmacist / Warehouse Manager |

#### Purchase Suggestion → Purchase Order

| # | Step | What happens | Who |
|---|---|---|---|
| 1 | New Purchase Suggestion | Pick the DC, the demand period (e.g. 30 days) and the date | Buyer |
| 2 | Generate Suggestions | System lists every item to reorder with its quantity, supplier, free goods and value | Automatic |
| 3 | Review | Buyer can change the quantity on any line | Buyer |
| 4 | Submit | The suggestion is locked | Buyer |
| 5 | Create Purchase Orders | One draft PO per preferred supplier, delivered to the DC | Automatic |
| 6 | Approve & send | PO priced from the rate contract, approved by value / category, then emailed to the supplier | Approvers |

**How the quantity is worked out**

| Rule | Calculation |
|---|---|
| Demand | Units sold by the stores the DC serves in the period + open online orders |
| Daily demand | Demand ÷ days in the period |
| Cover needed | Daily demand × (supplier lead time + safety days) |
| Safety days | Item setting, else by class: A = 7, B = 14, C = 30 |
| Available | DC stock + quantity still due on open POs |
| Order quantity | Cover needed − available, rounded up to the supplier's minimum order; nothing if stock is enough |
| Free goods | Supplier scheme at that quantity (e.g. 10+1) |

*Example:* Pan 40 sells 60 units a day, supplier lead time 3 days, class A (7 safety days) → needs 600; 150 in stock → order **450**.

#### Supplier workflow (order to payment)

```
SUPPLIER SET-UP ──▶ PO ──▶ APPROVAL ──▶ EMAIL ──▶ SUPPLIER ACK ──▶ GATE ENTRY ──▶ GRN ──▶ PUT-AWAY
                                                                                   │
                                     PAYMENT ◀── DEBIT NOTE (if any) ◀── SUPPLIER BILL (3-way match)
```

| # | Step | What happens | Status | Who |
|---|---|---|---|---|
| 1 | Supplier set-up | Supplier with GSTIN, drug / FSSAI licences, lead time, minimum order, payment terms and expiry-return terms. New or changed suppliers need approval | Master: Pending Approval → Approved | Buyer / Management or Compliance Pharmacist |
| 2 | Rate contract & schemes | Agreed PTR and trade discount per item with validity dates; schemes such as 10+1 free; cash discount through payment terms | — | Category Manager |
| 3 | Purchase order | From the Purchase Suggestion or by hand; one delivery warehouse per PO; priced from the rate contract. Supplier licence checked | Draft | Buyer |
| 4 | Approval | Approval matrix by value and category; Schedule X / narcotics need the Compliance Pharmacist; the creator can't approve | Pending → Approved / Rejected | Approvers |
| 5 | Send to supplier | On submit the PO is emailed as a PDF (can be resent) | Email: Sent / Failed | Automatic |
| 6 | Supplier acknowledges | Supplier logs in to the supplier portal, confirms the PO and an expected delivery date. Reminders go out if there's no reply | Email: Acknowledged | Supplier |
| 7 | Gate entry | Pick the PO (supplier and DC fill in), vehicle, supplier invoice no., cases | Arrived | Security / Inward QC |
| 8 | Goods receipt (GRN) | Gate Entry → **Create → Purchase Receipt**; scan each item with batch, mfg / expiry, MRP, free qty, invoiced qty, temperature for cold items. Blocked: not on PO, over the order, short shelf life, MRP above NPPA ceiling, cold item without reading. MRP change needs approval. Temperature breach → quarantine | GRN submitted | Inward QC |
| 9 | Discrepancy | Damage, shortage or excess recorded with photos; the note is emailed to the supplier | Discrepancy note sent | Inward QC / Buyer |
| 10 | Put-away | Bin suggested by zone, temperature and capacity; Schedule X / narcotics into the locked cage with register entry | Put away | Warehouse staff |
| 11 | Partial supply | PO stays open for the balance; backorders followed up automatically; **Short Close** with a reason when no more will come | To Receive / Closed | Buyer |
| 12 | Supplier bill | Purchase Invoice against the GRN; three-way match of PO rate, GRN quantity and billed quantity / rate | Matched / Under-billed / Debit Note Raised | Accounts |
| 13 | Debit note | Over-billing on rate or quantity creates a **draft debit note** for Accounts to review and submit | Draft → Submitted | Pharmacy Accounts |
| 14 | Payment | Pay the bill less debit notes and cash discount, by the payment terms | Paid | Accounts |
| 15 | Performance | Fill rate, on-time % and actual lead time per supplier, updated daily | Supplier Performance report | Buyer / Management |

### Flow 2 — Selling at the store

| # | Step | What happens | Who |
|---|---|---|---|
| 1 | Find | Search by barcode, brand or generic; see stock, batches, expiry, MRP, substitutes | Store Pharmacist |
| 2 | Batch | Earliest expiry by default; expired, recalled or held batches blocked | Automatic |
| 3 | Price | Never above MRP; loose strips / tablets from pack MRP; offers apply automatically | Automatic |
| 4 | Discount | Manual discount capped by role; above the cap needs approval | Area Manager |
| 5 | Prescription | Schedule H / H1 / X need prescription file, doctor name and registration no. | Store Pharmacist |
| 6 | Registers | Schedule H1 and X / narcotics registers filled from the bill | Automatic |
| 7 | Customer | Found by mobile number, with purchase history and saved prescriptions | Store Pharmacist |

### Flow 3 — Online orders (website)

```
/order ──▶ /cart ──▶ SALES ORDER ──▶ PAY ──▶ PICK & PACK ──▶ DELIVERY NOTE ──▶ DELIVERY TRIP ──▶ DELIVERED
                                                                                   └── store pickup: hand-over at counter ──┘
```

| # | Step | What happens | Online status | Who |
|---|---|---|---|---|
| 1 | Browse (`/order`) | Medicines by brand or generic, with price, Rx / OTC tag and filters | — | Customer |
| 2 | Cart (`/cart`) | Quantities; home delivery with full address (lines, postal code, city, state, optional GSTIN), saved to the customer automatically; or store pickup; prescription upload for Rx items (PDF / JPG / PNG, stored privately on the order); payment method | — | Customer |
| 3 | Order placed | A **Sales Order** is created with the delivery address and optional attached prescription file | Awaiting Payment (Razorpay) · Confirmed (COD) | Automatic |
| 4 | Pay online | Razorpay (UPI, card, net banking, wallet): Sales Order submitted, **Sales Invoice** and **Payment Entry** created automatically; customer emailed | Confirmed · Paid | Customer / Automatic |
| 5 | Cash on delivery | Open the Sales Order and **Submit** it | Confirmed | Store Pharmacist |
| 6 | Pick | Sales Order → **Create → Pick List**: earliest-expiry batches and bins suggested; picker enters the picked qty (in stock units) | **Picking** | Picker / Packer |
| 7 | Pack | Picker seals the bag / box, scans or enters its **Bag / Box Label** → **Submit** the Pick List; packer and time recorded; customer emailed | **Packed** | Picker / Packer |
| 8 | Delivery Note | Pick List → **Create → Delivery Note** (shipping address, batches from the pick) → **Submit**; stock leaves. **Orders from the DC must be picked first**; at a store the Pick List is optional and the pharmacist can make the Delivery Note from the Sales Order | Packed | Picker / Store Pharmacist |
| 9 | Dispatch | **Delivery Trip**: driver, vehicle, the Delivery Note as a stop (customer and address fill in automatically) → **Submit**; customer emailed | **Dispatched** (Partly Dispatched if not all items shipped) | Dispatch Coordinator |
| 10 | Deliver | The rider opens their trip (they see only their own), clicks **Mark Delivered → #stop** after hand-over; customer emailed | **Delivered** | Delivery Rider |
| 10b | Store pickup | No trip: submitting the Delivery Note is the hand-over | **Delivered** | Store Pharmacist |
| 11 | Bill COD orders | Delivery Note → **Create → Sales Invoice** → Submit; then **Create → Payment** for the cash collected | Delivered · Paid | Store Pharmacist / Accounts |
| 12 | Track (`/orders`) | Customer sees status, payment and prints the GST invoice | — | Customer |

**Rules**
- Schedule X and narcotic drugs are never sold online.
- Prescription files uploaded at checkout are stored against the Sales Order for pharmacist verification prior to dispatch.
- Cancelling a Delivery Trip puts the order back to *Packed* (or *Confirmed* if it was never picked).
- Online orders shipped from the DC can't get a Delivery Note until a Pick List has been submitted.
- The ERPNext order status turns *Completed* once the order is fully delivered and billed.

### Flow 4 — Returns and supplier credit

| # | Step | What happens | Who |
|---|---|---|---|
| 1 | Return | Stores send near-expiry, slow or damaged stock to the DC | Store Pharmacist / Area Manager |
| 2 | Inspect | Back to stock, return to supplier, or destroy | Compliance Pharmacist / Warehouse Manager |
| 3 | Credit | Debit note on the supplier within return terms | Accounts |

---

## 2. What Is Implemented

| Area | Features | Main screens |
|---|---|---|
| **Roles & masters** | 15 pharmacy roles; items with salt, strength, form, category, storage, pack units; batches with MRP and expiry; maker-checker approval on items, prices, suppliers, customers, stores | Item, Batch, Salt |
| **Compliance** | Drug licence matrix checked on every purchase, sale and transfer, expiry alerts 30/15/7 days; NPPA ceiling on batch MRP; shelf-life rules for receipts and dispatch | Drug Licence, NPPA Ceiling Price, Shelf Life Rule |
| **Replenishment** | Store order schedules and days; off-schedule approval; DC purchase suggestions; patient special orders | Replenishment Schedule, Purchase Suggestion, Patient Special Order |
| **Purchasing** | Approval matrix by value and category; rate contracts (PTR, trade discount, validity); schemes; cash discount; PO email and supplier acknowledgement; short close and backorder follow-up; fill rate, lead time, on-time | Purchase Order, PO Approval Matrix, Rate Contract, Supplier Performance |
| **Three-way match** | PO vs receipt vs bill; rate and qty differences raise debit notes | Purchase Invoice |
| **Inbound** | Gate entry from PO; scan and receive with automatic batches; receipt blocks and flags; cold-chain reading; discrepancy note to supplier | Gate Entry, Purchase Receipt, Receipt Discrepancy |
| **Quarantine** | QA release / return / destroy; quarantined stock can't be sold or shipped | Quarantine Decision |
| **Put-away & labels** | Directed put-away by zone, temperature, capacity; batch, GRN and bin labels | Put-away List |
| **Controlled drugs** | Locked cage, custodian-only moves; statutory register for receipts, transfers, sales, reversals | Controlled Drug Register |
| **Inventory control** | Stock by location with ageing and value; pick-face top-ups; blind cycle / full counts; adjustments with reason and approval; QC / recall / legal holds; near-expiry and slow-moving | Stock Count, Stock Hold, Pick Face |
| **DC outbound** | Pick waves by route; FEFO picking into typed totes; short picks (backorder / substitute / cancel); seals; challan or tax invoice; scheduled drugs on separate documents | Pick Wave, Tote |
| **Routes & trips** | Route with store sequence; trip with own / hired vehicle and driver; scan-to-load manifest; e-way bill details on departure; trip sheet | Delivery Route, Dispatch Trip |
| **Tote tracking** | Totes, crates, ice boxes issued, returned, missing by store; overdue alerts | Tote Movement, Tote Balance by Store |
| **Store receiving & transfers** | Shipments in transit with ETA; tote-scan receipt (tote-level or full); 24-hour discrepancy window and investigation; store-to-store transfers with approval; live store stock | Store Receipt, Transfer Discrepancy, Store Transfer Request |
| **Store billing (POS)** | Pharmacy search; FEFO batch; loose sale; MRP cap; offers and role-based discount limits with approval | Point of Sale, POS Discount Limit |
| **Prescriptions & customers** | Sale blocked without prescription for H / H1 / X; H1 register from the bill; customer by mobile; saved prescriptions; purchase history | Customer Prescription, Schedule H1 Register, Customer Purchase History |
| **Online orders** | Website catalogue, cart and order tracking pages; pincode delivery and store pickup; Razorpay and COD; automatic Sales Order, Sales Invoice and Payment Entry; pharmacist prescription check; delivery address saved; Dispatched / Delivered from Delivery Trip; order emails | `/order`, `/cart`, `/orders`, Sales Order (Online Order tab), Delivery Note, Delivery Trip, Online Order Settings |

---

## 3. Who Approves What

| What | Who approves |
|---|---|
| Purchase orders | By value: Buyer → Category Manager → Warehouse Manager → Management. Schedule X / narcotics: Compliance Pharmacist |
| New or changed masters | Management or Compliance Pharmacist |
| Extra store orders | Area Manager |
| Store discounts above the limit | Area Manager |
| Stock count differences, adjustments | Warehouse Manager; high value: Management |
| Quarantined stock | Compliance Pharmacist |
| Online prescription orders | Online Order Pharmacist |
| Store-to-store transfers | Area Manager (small patient transfers go through automatically) |

## 4. Controls That Always Apply

- Drug licences checked on every purchase, sale and transfer.
- NPPA price ceilings enforced on every batch MRP.
- Earliest-expiry stock moves first; near-expiry alerts at 180 / 90 / 60 / 30 days.
- Quarantine and holds stop stock from being sold or shipped.
- Controlled drugs stay in a locked cage; every movement is in the statutory register.
- Blind stock counts; every adjustment needs a reason and an approver.
- Totes, crates and ice boxes tracked by store.

## 5. Reports

Stock by Location · Near Expiry Stock · Slow and Non-Moving Stock · Supplier Performance · Shipments in Transit · Store Stock Overview · Tote Balance by Store · Schedule H1 Register · Customer Purchase History

---

*Step-by-step test instructions: `UI_TESTING_GUIDE_DETAILED.md`.*
