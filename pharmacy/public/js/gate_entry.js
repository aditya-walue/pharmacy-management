// Gate Entry — pick the PO (supplier, company and receiving DC fill in); start the GRN from here

frappe.ui.form.on("Gate Entry", {
	setup(frm) {
		frm.set_query("purchase_order", () => ({
			filters: { docstatus: 1, status: ["in", ["To Receive", "To Receive and Bill"]], ...(frm.doc.supplier ? { supplier: frm.doc.supplier } : {}) },
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Arrived" && frm.doc.purchase_order) {
			frm.add_custom_button(__("Purchase Receipt"), () =>
				frappe.model.open_mapped_doc({
					method: "pharmacy.pharmacy.doctype.gate_entry.gate_entry.make_purchase_receipt",
					frm,
				}), __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
	},
	purchase_order(frm) {
		if (!frm.doc.purchase_order) return;
		frappe.xcall("pharmacy.pharmacy.doctype.gate_entry.gate_entry.get_po_details", { purchase_order: frm.doc.purchase_order })
			.then((d) => frm.set_value(d));
	},
});
