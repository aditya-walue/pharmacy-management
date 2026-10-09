# Copyright (c) 2026, Aditya and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

SUPPLIER = "_Test Pharmacy Supplier"


def make_licence(**kwargs):
	return frappe.get_doc(
		{
			"doctype": "Drug Licence",
			"party_type": "Supplier",
			"party": SUPPLIER,
			"licence_form": "20B",
			"licence_no": "DL-TEST-1",
			"valid_from": add_days(today(), -365),
			"valid_upto": add_days(today(), 365),
			**kwargs,
		}
	).insert()


class TestDrugLicence(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_type": "Company"}
			).insert()

	def tearDown(self):
		frappe.db.delete("Drug Licence", {"party": SUPPLIER})

	def test_valid_upto_before_valid_from(self):
		with self.assertRaises(frappe.ValidationError):
			make_licence(valid_from=today(), valid_upto=add_days(today(), -1))

	def test_lapsed_licence_marked_expired(self):
		licence = make_licence(licence_no="DL-TEST-EXP", valid_upto=add_days(today(), -1))
		self.assertEqual(licence.status, "Expired")

	def test_expiring_licence_marked_expiring(self):
		licence = make_licence(licence_no="DL-TEST-EXPIRING", valid_upto=add_days(today(), 15))
		self.assertEqual(licence.status, "Expiring")

	def test_active_licence_marked_active(self):
		licence = make_licence(licence_no="DL-TEST-ACT", valid_upto=add_days(today(), 90))
		self.assertEqual(licence.status, "Active")

	def test_duplicate_licence_rejected(self):
		make_licence(licence_no="DL-TEST-DUP")
		with self.assertRaises(frappe.DuplicateEntryError):
			make_licence(licence_no="DL-TEST-DUP")


COMPLIANCE_USER = "test-compliance@pharmacy.example"


class TestLicenceExpiryJob(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_type": "Company"}
			).insert()
		if not frappe.db.exists("User", COMPLIANCE_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": COMPLIANCE_USER,
					"first_name": "Compliance",
					"send_welcome_email": 0,
					"roles": [{"role": "Compliance Pharmacist"}],
				}
			).insert()

	def tearDown(self):
		frappe.db.delete("Drug Licence", {"party": SUPPLIER})
		frappe.db.delete("Notification Log", {"for_user": COMPLIANCE_USER})

	def run_job(self, sendmail_error=None):
		from pharmacy.pharmacy.doctype.drug_licence.drug_licence import update_statuses_and_send_alerts

		with patch("frappe.sendmail", side_effect=sendmail_error) as sendmail:
			update_statuses_and_send_alerts()
		return sendmail

	def test_alerts_sent_only_at_30_15_and_7_days(self):
		# licences are named per party and form, so each needs its own form
		alerted = {
			make_licence(licence_no=f"DL-ALERT-{days}", licence_form=form, valid_upto=add_days(today(), days)).name
			for days, form in ((30, "20"), (15, "21"), (7, "20F"))
		}
		make_licence(licence_no="DL-ALERT-10", licence_form="21B", valid_upto=add_days(today(), 10))

		sendmail = self.run_job()

		self.assertEqual(self.notified(), alerted)
		self.assertEqual({call.kwargs["reference_name"] for call in sendmail.call_args_list}, alerted)
		for call in sendmail.call_args_list:
			self.assertIn(COMPLIANCE_USER, call.kwargs["recipients"])

	def test_email_failure_still_notifies_and_expires(self):
		alerted = make_licence(licence_no="DL-NO-EMAIL", valid_upto=add_days(today(), 7)).name
		lapsed = make_licence(licence_no="DL-NO-EMAIL-LAPSE", licence_form="21B", valid_upto=add_days(today(), 90))
		lapsed.db_set({"valid_upto": add_days(today(), -1), "status": "Active"})

		self.run_job(sendmail_error=frappe.OutgoingEmailError)

		self.assertEqual(self.notified(), {alerted})
		self.assertEqual(frappe.db.get_value("Drug Licence", lapsed.name, "status"), "Expired")

	def notified(self):
		return set(frappe.get_all("Notification Log", filters={"for_user": COMPLIANCE_USER}, pluck="document_name"))

	def test_job_marks_lapsed_licence_expired(self):
		licence = make_licence(licence_no="DL-LAPSE", valid_upto=add_days(today(), 90))
		# simulate time passing: Valid Upto is now behind us but nothing has re-saved the licence
		licence.db_set({"valid_upto": add_days(today(), -1), "status": "Active"})

		self.run_job()

		self.assertEqual(frappe.db.get_value("Drug Licence", licence.name, "status"), "Expired")
