// Tote — mark missing / found

frappe.ui.form.on("Tote", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (method, label, reqd) => frappe.prompt(
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks"), reqd },
			(v) => frappe.xcall(`pharmacy.overrides.tote_tracking.${method}`, { tote: frm.doc.name, remarks: v.remarks }).then(() => frm.reload_doc()),
			label, label);
		if (["At Store", "In Transit", "Dispatched"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Mark Missing"), () => call("mark_missing", __("Mark Missing"), 1));
		}
		if (frm.doc.status === "Missing") {
			frm.add_custom_button(__("Mark Found"), () => call("mark_found", __("Mark Found"), 0));
		}
	},
});
