// Stock Hold — release with a reason

frappe.ui.form.on("Stock Hold", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Active") return;
		frm.add_custom_button(__("Release Hold"), () => {
			frappe.prompt({ fieldname: "remarks", fieldtype: "Small Text", label: __("Release Remarks"), reqd: 1 },
				(v) => frappe
					.xcall("pharmacy.pharmacy.doctype.stock_hold.stock_hold.release_hold", { stock_hold: frm.doc.name, remarks: v.remarks })
					.then(() => frm.reload_doc()),
				__("Release Stock Hold"), __("Release"));
		});
	},
});
