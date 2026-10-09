// Customer — purchase history and saved prescriptions

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Purchase History"), () =>
			frappe.set_route("query-report", "Customer Purchase History", { customer: frm.doc.name }), __("Pharmacy"));
		frm.add_custom_button(__("Prescriptions"), () =>
			frappe.set_route("List", "Customer Prescription", { customer: frm.doc.name }), __("Pharmacy"));
		frm.add_custom_button(__("New Prescription"), () =>
			frappe.new_doc("Customer Prescription", { customer: frm.doc.name, patient_name: frm.doc.customer_name }), __("Pharmacy"));
	},
});
