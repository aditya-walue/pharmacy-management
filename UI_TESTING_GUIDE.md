# Pharmacy System — How It Works

One system runs the whole chain: buying from suppliers, the central warehouse (DC), delivery to stores, store billing and online orders. Every step is checked against drug laws and approved by the right person. The person who creates a record can never approve it.

```
SUPPLIER ──▶ WAREHOUSE (DC) ──▶ DELIVERY TRIP ──▶ STORE ──▶ PATIENT
                 ▲                                  │
                 └────── store sales = demand ──────┘
                                ONLINE ORDER ──▶ nearest store / DC ──▶ PATIENT
```

---

## Flow 1 — Buying and stocking the stores

| Step | What happens | Who |
|---|---|---|
| 1. Plan | The system suggests what to buy, from store sales, online orders, stock in hand, supplier lead time and minimum order quantities | Buyer |
| 2. Order | One purchase order per supplier, priced from the agreed rate contract, with schemes such as 10+1 free | Buyer |
| 3. Approve | Approval by order value; controlled drugs always need the Compliance Pharmacist | Category Manager / Warehouse Manager / Management |
| 4. Send | The order is emailed to the supplier, who confirms the delivery date. Late or short supplies are followed up | Automatic |
| 5. Gate entry | The vehicle, supplier invoice and number of cases are recorded on arrival | Security / Inward QC |
| 6. Receive and check | Each item is scanned with its batch, expiry and MRP. Wrong items, excess, short expiry or MRP above the government ceiling are blocked. Cold items need a temperature reading; a breach goes to quarantine | Inward QC |
| 7. Store in the DC | The system suggests the right shelf (cold room, general, locked cage for Schedule X / narcotics) | Warehouse staff |
| 8. Supplier bill | The bill is matched with the order and the receipt; differences raise a debit note | Accounts |
| 9. Store orders | Stores order on their fixed days; extra orders need Area Manager approval | Store Pharmacist |
| 10. Pick and pack | Earliest-expiry stock is picked into sealed totes, cold items into ice boxes | Picker / Packer |
| 11. Dispatch | Delivery challan or tax invoice with e-way bill; route, vehicle, driver and trip sheet | Dispatch Coordinator |
| 12. Store receives | The store scans its totes and checks seals. Differences reported within 24 hours are investigated and settled | Store Pharmacist / Warehouse Manager |

## Flow 2 — Selling at the store

| Step | What happens | Who |
|---|---|---|
| 1. Find the medicine | Search by barcode, brand or generic name; the screen shows stock, batches, expiry, MRP and cheaper substitutes | Store Pharmacist |
| 2. Batch | The earliest-expiry batch is chosen by default. Expired, recalled or held batches can't be sold | Automatic |
| 3. Price | The price is never above MRP. Loose strips and tablets are priced from the pack MRP. Offers apply automatically | Automatic |
| 4. Discounts | Extra discount is capped by role; anything above the cap needs a manager's approval | Area Manager |
| 5. Prescription | Schedule H / H1 / X medicines need the prescription, doctor name and registration number, or the bill is blocked | Store Pharmacist |
| 6. Registers | The Schedule H1 register (and the X / narcotics register) is filled automatically from the bill | Automatic |
| 7. Customer | Customers are found by mobile number, with their purchase history and saved prescriptions | Store Pharmacist |

## Flow 3 — Online orders

| Step | What happens | Who |
|---|---|---|
| 1. Browse | The website shows medicines by brand or generic name, with MRP, offers and substitutes. Schedule X and narcotics are never sold online | Customer |
| 2. Delivery check | Pincode shows whether delivery is available, the delivery time and COD, or the stores for pickup | Customer |
| 3. Cart and pay | Cart with coupons and loyalty points; pay by UPI, card, net banking or wallet (Razorpay), or cash on delivery | Customer |
| 4. Prescription | Prescription medicines are released only after a pharmacist checks the uploaded prescription; every check is logged | Online Order Pharmacist |
| 5. Allocate | The order goes to the nearest store with stock, or the DC. If one place can't fill it, it is split or a transfer is raised | Automatic |
| 6. Bill and deliver | The store or DC that ships bills it from its own stock, under its own GST registration; then marks it delivered or picked up | Store Pharmacist |
| 7. Track | The customer sees order status, invoices and pending payments | Customer |

## Flow 4 — Returns and supplier credit

| Step | What happens | Who |
|---|---|---|
| 1. Return | Stores send near-expiry, slow or damaged stock back to the DC | Store Pharmacist / Area Manager |
| 2. Inspect | The DC checks the stock and decides: back to stock, return to supplier, or destroy | Compliance Pharmacist / Warehouse Manager |
| 3. Credit | A debit note is raised on the supplier within the agreed return terms | Accounts |

---

## Who approves what

| What | Who approves |
|---|---|
| Purchase orders | By value: Buyer → Category Manager → Warehouse Manager → Management. Schedule X / narcotics: Compliance Pharmacist |
| New or changed masters (items, prices, suppliers, customers, stores) | Management or Compliance Pharmacist |
| Extra store orders | Area Manager |
| Store discounts above the limit | Area Manager |
| Stock count differences and adjustments | Warehouse Manager; high value: Management |
| Quarantined stock | Compliance Pharmacist |
| Online prescription orders | Online Order Pharmacist |
| Store-to-store transfers | Area Manager (small patient transfers go through automatically) |

## Controls that always apply

- **Drug licences** of suppliers, customers, the DC and stores are checked on every purchase, sale and transfer, with expiry alerts.
- **Government price ceilings (NPPA)** are enforced on every batch MRP.
- **Expiry**: earliest-expiry stock moves first; near-expiry alerts at 180, 90, 60 and 30 days.
- **Quarantine and holds** (QC, recall, legal) stop stock from being sold or shipped.
- **Controlled drugs** stay in a locked cage, and every movement is written to the statutory register.
- **Stock counts** are done blind, and every adjustment needs a reason and an approver.
- **Totes, crates and ice boxes** are tracked by store: issued, returned or missing.

## Main reports

Stock by location · Near-expiry stock · Slow and non-moving stock · Supplier performance · Shipments in transit · Store stock overview · Tote balance by store · Schedule H1 register · Customer purchase history

---

*The detailed step-by-step test guide is in `UI_TESTING_GUIDE_DETAILED.md`.*
