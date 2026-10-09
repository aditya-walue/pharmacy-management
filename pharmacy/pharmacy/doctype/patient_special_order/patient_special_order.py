# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

# Patient Special Order doctype has been retired.
# Patient special orders are now tracked directly on Sales Order using:
#   nir_is_patient_special_order (Check)
#   nir_patient_name, nir_patient_phone, nir_store, nir_priority, nir_pso_status
#
# Lifecycle tracking is handled in pharmacy.overrides.patient_order.

import frappe
from frappe.model.document import Document


class PatientSpecialOrder(Document):
    pass
