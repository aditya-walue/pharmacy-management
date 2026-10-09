# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate

DEFAULT_VALIDITY_DAYS = 180


class CustomerPrescription(Document):
	def validate(self):
		if not self.patient_name:
			self.patient_name = frappe.db.get_value("Customer", self.customer, "customer_name")
		if not self.valid_upto:
			self.valid_upto = add_days(self.prescription_date, DEFAULT_VALIDITY_DAYS)
		if getdate(self.valid_upto) < getdate(self.prescription_date):
			frappe.throw(_("Valid Upto cannot be before the prescription date"))
