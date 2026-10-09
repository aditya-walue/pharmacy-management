# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class PurchaseSuggestion(Document):
    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def validate(self):
        if not self.as_of_date:
            self.as_of_date = today()
        if not self.period_days or self.period_days < 1:
            self.period_days = 30
        self._update_summary()

    def on_submit(self):
        self.db_set("status", "Submitted")

    def on_cancel(self):
        self.db_set("status", "Draft")

    # -----------------------------------------------------------------------
    # Summary roll-up
    # -----------------------------------------------------------------------

    def _update_summary(self):
        self.total_items = len([r for r in self.items if flt(r.ordered_qty) > 0])
        self.total_estimated_value = sum(flt(r.estimated_value) for r in self.items)

    # -----------------------------------------------------------------------
    # Generate suggestions (called from client JS)
    # -----------------------------------------------------------------------

    @frappe.whitelist()
    def generate(self):
        """
        Populate the items table by running the purchase suggestion engine.
        Clears any existing rows, then appends one row per item that needs replenishment.
        """
        if self.docstatus == 1:
            frappe.throw(_("Cannot re-generate suggestions on a submitted document."))

        from pharmacy.pharmacy.purchase_suggestion_engine import generate_suggestions

        rows = generate_suggestions(
            warehouse=self.warehouse,
            period_days=self.period_days or 30,
            as_of_date=self.as_of_date or today(),
        )

        self.items = []
        for r in rows:
            self.append("items", r)

        self._update_summary()
        self.save()
        frappe.msgprint(
            _("Generated {0} purchase suggestion(s) for {1}.").format(len(rows), self.warehouse),
            title=_("Suggestions Generated"),
            indicator="green",
        )
        return {"count": len(rows)}

    # -----------------------------------------------------------------------
    # Create Purchase Orders (called from client JS)
    # -----------------------------------------------------------------------

    @frappe.whitelist()
    def make_purchase_orders(self):
        """
        Group items by preferred_supplier → create one PO per supplier for this
        suggestion's warehouse (POs are raised per warehouse and supplier).
        Items without a preferred supplier are skipped (warning shown).

        Returns list of created PO names.
        """
        if self.docstatus != 1:
            frappe.throw(_("Submit the Purchase Suggestion before creating Purchase Orders."))
        if self.status == "PO Created":
            frappe.throw(_("Purchase Orders have already been created for this suggestion."))

        company = frappe.db.get_value("Warehouse", self.warehouse, "company")
        items_by_supplier: dict[str, list] = {}
        no_supplier = []

        for row in self.items:
            if flt(row.ordered_qty) <= 0:
                continue
            if not row.preferred_supplier:
                no_supplier.append(row.item_code)
                continue
            items_by_supplier.setdefault(row.preferred_supplier, []).append(row)

        if no_supplier:
            frappe.msgprint(
                _("The following items were skipped (no preferred supplier): {0}").format(
                    ", ".join(no_supplier)
                ),
                title=_("Skipped Items"),
                indicator="orange",
            )

        created_pos = []
        for supplier, rows in items_by_supplier.items():
            po = frappe.get_doc(
                {
                    "doctype": "Purchase Order",
                    "supplier": supplier,
                    "company": company,
                    "set_warehouse": self.warehouse,
                    "transaction_date": today(),
                    "schedule_date": today(),
                    "items": [
                        {
                            "item_code": r.item_code,
                            "qty": flt(r.ordered_qty),
                            "uom": r.uom,
                            # undiscounted: the rate contract and Pricing Rule schemes price the PO,
                            # so a scheme-discounted estimate here would discount twice
                            "rate": flt(r.last_purchase_rate),
                            "warehouse": self.warehouse,
                            "schedule_date": today(),
                        }
                        for r in rows
                    ],
                }
            )
            po.flags.ignore_permissions = True
            po.insert()
            created_pos.append(po.name)

        if created_pos:
            self.db_set("status", "PO Created")
            frappe.msgprint(
                _("Created Purchase Orders: {0}").format(", ".join(created_pos)),
                title=_("Purchase Orders Created"),
                indicator="green",
            )

        return created_pos
