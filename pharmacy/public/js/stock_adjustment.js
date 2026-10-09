// Stock Entry / Stock Reconciliation — adjustment approval (reason code + approver other than the maker)

["Stock Entry", "Stock Reconciliation"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			const pending = frm.doc.docstatus === 0 && !frm.is_new() && !frm.is_dirty()
				&& frm.doc.nir_reason_code && frm.doc.nir_adjustment_approver_role && !frm.doc.nir_adjustment_approved_by;
			if (!pending || frappe.session.user === frm.doc.owner) return;

			const role = frm.doc.nir_adjustment_approver_role;
			const allowed = frappe.user.has_role(role) || frappe.user.has_role("System Manager")
				|| (role === "Warehouse Manager" && frappe.user.has_role("Pharmacy Management"));
			if (!allowed) return;

			frm.add_custom_button(__("Approve Adjustment"), () => {
				frappe
					.xcall("pharmacy.overrides.stock_adjustment.approve_adjustment", { doctype, name: frm.doc.name })
					.then(() => frm.reload_doc());
			});
		},
	});
});
