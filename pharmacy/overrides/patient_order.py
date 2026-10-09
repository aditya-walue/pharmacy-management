"""
Patient Order Override
======================
Handles Patient Special Order fields directly on Sales Order.

Lifecycle (nir_pso_status on Sales Order):
  Draft → Requested → PO Issued → Received at DC → Ready for Pickup → Completed

When nir_is_patient_special_order == 1 on the Sales Order:
  - nir_patient_name and nir_store are mandatory.
  - nir_priority defaults to High.

Linked documents (Material Request, Purchase Order, Purchase Receipt,
Stock Entry, Sales Invoice, POS Invoice) carry nir_patient_sales_order
back to the originating Sales Order so we can update nir_pso_status.
"""

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Sales Order hooks
# ---------------------------------------------------------------------------

def validate_patient_order(doc, method=None):
    """Validate that mandatory patient fields are filled when PSO flag is set."""
    if not doc.nir_is_patient_special_order:
        return

    if not doc.nir_patient_name:
        frappe.throw(_("Patient Name is required for a Patient Special Order."), title=_("Missing Patient Info"))

    if not doc.nir_store:
        frappe.throw(_("Pharmacy Store is required for a Patient Special Order."), title=_("Missing Patient Info"))

    # Ensure priority has a sensible default
    if not doc.nir_priority:
        doc.nir_priority = "High"


# ---------------------------------------------------------------------------
# Lifecycle tracking hook (called on PO / PR / SE / SI / POS Invoice submit)
# ---------------------------------------------------------------------------

def update_patient_so_tracking(doc, method=None):
    """
    Called on on_submit of:
      Purchase Order    → PO Issued
      Purchase Receipt  → Received at DC
      Stock Entry (Material Transfer) → Ready for Pickup
      Sales Invoice / POS Invoice → Completed

    The linked Sales Order is identified via doc.nir_patient_sales_order.
    """
    so_name = doc.get("nir_patient_sales_order")
    if not so_name:
        return

    # Verify the SO is actually a patient special order
    is_pso = frappe.db.get_value("Sales Order", so_name, "nir_is_patient_special_order")
    if not is_pso:
        return

    doctype = doc.doctype

    if doctype == "Purchase Order":
        frappe.db.set_value("Sales Order", so_name, "nir_pso_status", "PO Issued")

    elif doctype == "Purchase Receipt":
        frappe.db.set_value("Sales Order", so_name, "nir_pso_status", "Received at DC")

    elif doctype == "Stock Entry" and doc.get("purpose") == "Material Transfer":
        frappe.db.set_value("Sales Order", so_name, "nir_pso_status", "Ready for Pickup")
        so_doc = frappe.get_doc("Sales Order", so_name)
        frappe.msgprint(
            _(
                "Patient Special Order {0} is READY FOR PICKUP at store {1}! "
                "Contact patient {2} ({3})."
            ).format(
                so_name,
                so_doc.nir_store,
                so_doc.nir_patient_name,
                so_doc.nir_patient_phone or "—",
            ),
            title=_("Patient Order Ready for Pickup"),
            indicator="green",
        )

    elif doctype in ("Sales Invoice", "POS Invoice"):
        frappe.db.set_value("Sales Order", so_name, "nir_pso_status", "Completed")
