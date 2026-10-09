// Stock Count — get lines, blind scan counting on the handheld, variance approval

frappe.ui.form.on("Stock Count", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Lines"), () => {
				frm.call({ method: "get_lines", doc: frm.doc, freeze: true }).then(() => frm.reload_doc());
			});
			if (!frm.is_new()) {
				frm.add_custom_button(__("Scan Count"), () => scan_count(frm)).addClass("btn-primary");
			}
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Pending Approval") {
			for (const action of ["Approve", "Reject"]) {
				frm.add_custom_button(__(action), () => {
					const go = (remarks) =>
						frappe
							.xcall("pharmacy.pharmacy.doctype.stock_count.stock_count.act_on_count", {
								stock_count: frm.doc.name,
								action,
								remarks,
							})
							.then(() => frm.reload_doc());
					if (action === "Reject") {
						frappe.prompt({ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
							(v) => go(v.remarks), __("Reject Count"), __("Reject"));
					} else {
						frappe.confirm(__("Approve and post the variances as a Stock Reconciliation?"), () => go());
					}
				}, __("Variance"));
			}
		}
	},
});

frappe.ui.form.on("Stock Count Item", {
	counted_qty(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "counted", 1);
		frappe.model.set_value(cdt, cdn, "counted_by", frappe.session.user);
	},
});

function scan_count(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Scan Count"),
		fields: [
			{ fieldname: "bin", fieldtype: "Data", label: __("1. Scan Bin"), reqd: 1 },
			{ fieldname: "code", fieldtype: "Data", label: __("2. Scan Batch / Item"), reqd: 1 },
			{ fieldname: "qty", fieldtype: "Float", label: __("3. Qty Counted"), reqd: 1 },
			{ fieldname: "last", fieldtype: "HTML" },
		],
		primary_action_label: __("Record"),
		primary_action(values) {
			frappe
				.xcall("pharmacy.pharmacy.doctype.stock_count.stock_count.record_count", {
					stock_count: frm.doc.name,
					bin_code: values.bin.trim(),
					code: values.code.trim(),
					qty: values.qty,
				})
				.then((r) => {
					dialog.fields_dict.last.$wrapper.html(
						`<div class="small text-success">${__("Recorded {0} {1} — {2} of {3} lines counted", [
							r.item_code, r.batch_no || "", r.counted, r.total,
						])}</div>`
					);
					// same bin is usually counted item after item
					dialog.set_value("code", "");
					dialog.set_value("qty", null);
					dialog.fields_dict.code.set_focus();
					frm.reload_doc();
				});
		},
	});
	dialog.fields_dict.bin.$input.on("change", () => dialog.fields_dict.code.set_focus());
	dialog.fields_dict.code.$input.on("change", () => dialog.fields_dict.qty.set_focus());
	dialog.show();
	dialog.fields_dict.bin.set_focus();
}
