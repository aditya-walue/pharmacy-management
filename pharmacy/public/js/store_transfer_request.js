// Store Transfer Request — request approval, approve/reject, dispatch

const STR = "pharmacy.pharmacy.doctype.store_transfer_request.store_transfer_request";

frappe.ui.form.on("Store Transfer Request", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		const s = frm.doc.status;
		if (s === "Draft") {
			frm.add_custom_button(__("Request Approval"), () =>
				frappe.xcall(`${STR}.request_approval`, { request: frm.doc.name }).then(() => frm.reload_doc())).addClass("btn-primary");
		}
		if (s === "Pending Approval" && frappe.session.user !== frm.doc.owner
			&& (frappe.user.has_role("Area Manager") || frappe.user.has_role("System Manager"))) {
			frm.add_custom_button(__("Approve"), () =>
				frappe.xcall(`${STR}.decide`, { request: frm.doc.name, action: "Approve" }).then(() => frm.reload_doc()), __("Decision"));
			frm.add_custom_button(__("Reject"), () => frappe.prompt({ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				(v) => frappe.xcall(`${STR}.decide`, { request: frm.doc.name, action: "Reject", remarks: v.remarks }).then(() => frm.reload_doc())), __("Decision"));
		}
		if (s === "Approved") {
			frm.add_custom_button(__("Dispatch"), () =>
				frappe.xcall(`${STR}.dispatch`, { request: frm.doc.name }).then((name) => {
					frappe.msgprint(__("Dispatched on {0}", [name]));
					frm.reload_doc();
				})).addClass("btn-primary");
		}
	},
});
