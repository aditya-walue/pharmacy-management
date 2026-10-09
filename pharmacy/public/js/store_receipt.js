// Store Receipt — tote scan with seal check, item scan for full checks

const SR = "pharmacy.pharmacy.doctype.store_receipt.store_receipt";

frappe.ui.form.on("Store Receipt", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.is_new() || frm.is_dirty()) return;
		if ((frm.doc.totes || []).length) {
			frm.add_custom_button(__("Scan Totes"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Scan Totes"),
					fields: [
						{ fieldname: "seal", fieldtype: "Select", label: __("Seal"), options: "Intact\nBroken", default: "Intact" },
						{ fieldname: "tote", fieldtype: "Data", label: __("Scan Tote") },
						{ fieldname: "last", fieldtype: "HTML" },
					],
				});
				d.fields_dict.tote.$input.on("change", () => {
					const tote = (d.get_value("tote") || "").trim();
					if (!tote) return;
					frappe.xcall(`${SR}.scan_tote`, { receipt: frm.doc.name, tote, seal_intact: d.get_value("seal") })
						.then((r) => d.fields_dict.last.$wrapper.html(`<div class="small ${r.seal === "Intact" ? "text-success" : "text-danger"}">${__("{0}: seal {1} — {2} of {3} totes", [tote, r.seal, r.scanned, r.of])}</div>`))
						.finally(() => { d.set_value("tote", ""); d.set_value("seal", "Intact"); d.fields_dict.tote.set_focus(); frm.reload_doc(); });
				});
				d.show();
				d.fields_dict.tote.set_focus();
			}).addClass("btn-primary");
		}
		frm.add_custom_button(__("Scan Items"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Count Items"),
				fields: [
					{ fieldname: "code", fieldtype: "Data", label: __("Scan Batch / Item"), reqd: 1 },
					{ fieldname: "qty", fieldtype: "Float", label: __("Qty Received (incl. damaged)"), reqd: 1 },
					{ fieldname: "damaged", fieldtype: "Float", label: __("Of which Damaged") },
					{ fieldname: "last", fieldtype: "HTML" },
				],
				primary_action_label: __("Record"),
				primary_action(v) {
					frappe.xcall(`${SR}.scan_item`, { receipt: frm.doc.name, code: v.code, qty: v.qty, damaged_qty: v.damaged || 0 })
						.then((r) => {
							d.fields_dict.last.$wrapper.html(`<div class="small text-success">${__("{0} recorded — {1} of {2} lines checked", [r.item_code, r.checked, r.of])}</div>`);
							["code", "qty", "damaged"].forEach((f) => d.set_value(f, null));
							d.fields_dict.code.set_focus();
							frm.reload_doc();
						});
				},
			});
			d.fields_dict.code.$input.on("change", () => d.fields_dict.qty.set_focus());
			d.show();
			d.fields_dict.code.set_focus();
		});
	},
});
