// Put-away List — scan the batch label, then the bin it went into

frappe.ui.form.on("Put-away List", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.is_new()) return;
		frm.add_custom_button(__("Scan Put-away"), () => scan_putaway(frm)).addClass("btn-primary");
	},
});

function scan_putaway(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Scan Put-away"),
		fields: [
			{ fieldname: "code", fieldtype: "Data", label: __("1. Scan Batch / Item Label"), reqd: 1 },
			{ fieldname: "bin", fieldtype: "Data", label: __("2. Scan Bin Label"), reqd: 1 },
			{ fieldname: "last", fieldtype: "HTML" },
		],
	});

	dialog.fields_dict.code.$input.on("change", () => dialog.fields_dict.bin.set_focus());
	dialog.fields_dict.bin.$input.on("change", () => {
		const code = (dialog.get_value("code") || "").trim();
		const bin = (dialog.get_value("bin") || "").trim();
		if (!code || !bin) return;

		frappe
			.xcall("pharmacy.pharmacy.doctype.put_away_list.put_away_list.confirm_scan", {
				putaway: frm.doc.name,
				code,
				bin_code: bin,
			})
			.then((r) => {
				const note = r.moved ? ` <span class="text-warning">${__("(not the suggested bin)")}</span>` : "";
				dialog.fields_dict.last.$wrapper.html(
					`<div class="small text-success">${__("Line {0}: {1} put into {2}", [r.idx, r.item_code, r.bin])}${note}</div>`
				);
				frm.reload_doc();
			})
			.finally(() => {
				dialog.set_value("code", "");
				dialog.set_value("bin", "");
				dialog.fields_dict.code.set_focus();
			});
	});

	dialog.show();
	dialog.fields_dict.code.set_focus();
}
