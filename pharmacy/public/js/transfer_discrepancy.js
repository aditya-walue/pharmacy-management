// Transfer Discrepancy — investigate, findings, approval

const TD = "pharmacy.pharmacy.doctype.transfer_discrepancy.transfer_discrepancy";

frappe.ui.form.on("Transfer Discrepancy", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		const call = (method, args) => frappe.xcall(`${TD}.${method}`, { discrepancy: frm.doc.name, ...args }).then(() => frm.reload_doc());
		if (frm.doc.status === "Open" && (frappe.user.has_role("Warehouse Manager") || frappe.user.has_role("System Manager"))) {
			frm.add_custom_button(__("Start Investigation"), () => call("start_investigation"));
		}
		if (frm.doc.status === "Under Investigation" && frm.doc.investigated_by === frappe.session.user) {
			frm.add_custom_button(__("Submit Findings"), () => call("submit_findings")).addClass("btn-primary");
		}
		if (frm.doc.status === "Pending Approval" && ![frm.doc.investigated_by, frm.doc.owner].includes(frappe.session.user)) {
			frm.add_custom_button(__("Approve & Adjust"), () =>
				frappe.confirm(__("Approve the findings and post the stock adjustments?"), () => call("decide", { action: "Approve" })), __("Decision"));
			frm.add_custom_button(__("Send Back"), () => frappe.prompt({ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				(v) => call("decide", { action: "Reject", remarks: v.remarks }), __("Send Back to Warehouse")), __("Decision"));
		}
	},
});
