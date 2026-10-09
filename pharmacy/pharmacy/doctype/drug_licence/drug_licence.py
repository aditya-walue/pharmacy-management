# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, getdate, today

ALERT_DAYS = (30, 15, 7)
EXPIRING_DAYS = 30
COMPLIANCE_ROLE = "Compliance Pharmacist"


class DrugLicence(Document):
	def validate(self):
		if getdate(self.valid_upto) < getdate(self.valid_from):
			frappe.throw(_("Valid Upto cannot be before Valid From"), frappe.ValidationError)

		self.validate_duplicate()
		self.update_expiry_status()

	def validate_duplicate(self):
		duplicate = frappe.db.exists(
			"Drug Licence",
			{
				"party_type": self.party_type,
				"party": self.party,
				"licence_form": self.licence_form,
				"licence_no": self.licence_no,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("{0} {1} already exists for {2}").format(self.licence_form, self.licence_no, self.party),
				frappe.DuplicateEntryError,
			)

	def update_expiry_status(self):
		self.status = get_status(self.valid_upto)


def get_status(valid_upto):
	"""Expired after Valid Upto, Expiring within EXPIRING_DAYS of it, otherwise Active."""
	today_date = getdate(today())
	upto_date = getdate(valid_upto)
	if upto_date < today_date:
		return "Expired"
	if upto_date <= add_days(today_date, EXPIRING_DAYS):
		return "Expiring"
	return "Active"


def update_statuses_and_send_alerts():
	"""Daily: move licences to Expiring/Expired and alert Compliance at 30, 15 and 7 days to expiry."""
	for licence in frappe.get_all(
		"Drug Licence", filters={"status": ("!=", "Expired")}, fields=["name", "valid_upto", "status"]
	):
		status = get_status(licence.valid_upto)
		if status != licence.status:
			frappe.db.set_value("Drug Licence", licence.name, "status", status)

	expiring = frappe.get_all(
		"Drug Licence",
		filters={"valid_upto": ("in", [add_days(today(), days) for days in ALERT_DAYS])},
		fields=["name", "party_type", "party", "licence_form", "licence_no", "valid_upto"],
	)
	recipients = get_compliance_users()
	if not expiring or not recipients:
		return

	for licence in expiring:
		send_expiry_alert(licence, recipients)


def send_expiry_alert(licence, recipients):
	days_left = date_diff(licence.valid_upto, today())
	subject = _("Licence {0} for {1} expires in {2} days").format(licence.licence_no, licence.party, days_left)
	message = _("Form {0} licence {1} held by {2} {3} is valid until {4}. Renew it before it lapses.").format(
		licence.licence_form,
		licence.licence_no,
		licence.party_type,
		licence.party,
		frappe.format(licence.valid_upto, "Date"),
	)

	# in-app alerts go first; a missing or broken email account must not suppress them
	for user in recipients:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Drug Licence",
				"document_name": licence.name,
				"subject": subject,
				"email_content": message,
			}
		).insert(ignore_permissions=True)

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype="Drug Licence",
			reference_name=licence.name,
		)
	except frappe.OutgoingEmailError:
		frappe.log_error(title=_("Licence expiry email not sent"), reference_doctype="Drug Licence", reference_name=licence.name)


def get_compliance_users():
	users = frappe.get_all(
		"Has Role", filters={"role": COMPLIANCE_ROLE, "parenttype": "User"}, pluck="parent", distinct=True
	)
	return frappe.get_all("User", filters={"name": ("in", users), "enabled": 1}, pluck="name") if users else []
