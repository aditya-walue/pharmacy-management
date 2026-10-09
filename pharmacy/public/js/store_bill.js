// POS Invoice / Sales Invoice — approve a discount above the cashier's limit

["POS Invoice", "Sales Invoice"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.doc.docstatus !== 0 || frm.doc.nir_discount_approval !== "Pending" || frm.is_dirty()) return;
			if (frappe.session.user === frm.doc.owner) {
				frm.dashboard.set_headline(__("Discount of {0}% is waiting for approval.", [frm.doc.nir_discount_requested]), "orange");
				return;
			}
			frm.add_custom_button(__("Approve Discount"), () =>
				frappe.xcall("pharmacy.overrides.pos_billing.approve_discount", { doctype, name: frm.doc.name }).then(() => frm.reload_doc()));
		},
	});
});

// Saved prescriptions: only the customer's own, still valid; picking one fills the prescription details
["POS Invoice", "Sales Invoice"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		setup(frm) {
			frm.set_query("nir_customer_prescription", () => ({
				filters: { customer: frm.doc.customer, valid_upto: [">=", frm.doc.posting_date || frappe.datetime.get_today()] },
			}));
		},
		nir_customer_prescription(frm) {
			if (!frm.doc.nir_customer_prescription) return;
			frappe.db.get_doc("Customer Prescription", frm.doc.nir_customer_prescription).then((rx) =>
				frm.set_value({
					nir_prescription: rx.prescription_file, nir_doctor_name: rx.doctor_name, nir_doctor_reg_no: rx.doctor_reg_no,
					nir_patient_name: rx.patient_name, nir_patient_address: rx.patient_address,
				}));
		},
	});
});
