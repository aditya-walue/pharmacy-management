// Purchase Order — approval buttons (PO Approval Matrix) and supplier dispatch / acknowledgement

frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.is_dirty()) return;
		add_approval_buttons(frm);
		add_supplier_buttons(frm);
		add_short_close_button(frm);
	},
});

function add_short_close_button(frm) {
	if (frm.doc.docstatus !== 1 || !["To Receive", "To Receive and Bill"].includes(frm.doc.status)) return;

	// ERPNext's own Close is refused while goods are pending; this records why the rest won't come
	frm.add_custom_button(__("Short Close"), () => {
		frappe.prompt(
			[
				{
					fieldname: "reason",
					fieldtype: "Select",
					label: __("Reason"),
					reqd: 1,
					options: [
						"",
						"Supplier cannot supply",
						"Product discontinued",
						"Price changed",
						"Bought substitute",
						"Other",
					].join("\n"),
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks"),
					mandatory_depends_on: "eval:doc.reason=='Other'",
				},
			],
			(values) => {
				frappe
					.xcall("pharmacy.overrides.po_fulfilment.short_close", {
						purchase_order: frm.doc.name,
						...values,
					})
					.then(() => frm.reload_doc());
			},
			__("Short Close Purchase Order"),
			__("Short Close")
		);
	}, __("Status"));
}

function add_approval_buttons(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.nir_approval_status !== "Pending") return;

	frappe
		.xcall("pharmacy.overrides.po_approval.get_actionable_rows", {
			purchase_order: frm.doc.name,
		})
		.then((rows) => {
			if (!rows || !rows.length) return;

			frm.add_custom_button(__("Approve"), () => act(frm, "Approve"), __("Approval"));
			frm.add_custom_button(__("Reject"), () => {
				frappe.prompt(
					{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					(values) => act(frm, "Reject", values.remarks),
					__("Reject Purchase Order"),
					__("Reject")
				);
			}, __("Approval"));
		});
}

function act(frm, action, remarks) {
	frappe
		.xcall("pharmacy.overrides.po_approval.act_on_purchase_order", {
			purchase_order: frm.doc.name,
			action,
			remarks,
		})
		.then((status) => {
			frappe.show_alert({ message: __("Approval status: {0}", [__(status)]), indicator: "green" });
			frm.reload_doc();
		});
}

function add_supplier_buttons(frm) {
	if (frm.doc.docstatus !== 1 || ["Closed", "Completed"].includes(frm.doc.status)) return;

	frm.add_custom_button(__("Send to Supplier"), () => {
		frappe
			.xcall("pharmacy.overrides.po_dispatch.resend_po", { purchase_order: frm.doc.name })
			.then((status) => {
				frappe.show_alert({
					message: status === "Sent" ? __("Emailed to supplier") : __("Could not email the supplier; see the timeline"),
					indicator: status === "Sent" ? "green" : "red",
				});
				frm.reload_doc();
			});
	}, __("Supplier"));

	frm.add_custom_button(__("Record Acknowledgement"), () => {
		frappe.prompt(
			[
				{
					fieldname: "expected_delivery_date",
					fieldtype: "Date",
					label: __("Expected Delivery Date"),
					reqd: 1,
					default: frm.doc.nir_expected_delivery_date || frm.doc.schedule_date,
					description: __("Applies to every line. Suppliers can give per-line dates on the portal."),
				},
				{
					fieldname: "confirmation_no",
					fieldtype: "Data",
					label: __("Supplier Confirmation No"),
					default: frm.doc.order_confirmation_no,
				},
				{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
			],
			(values) => {
				frappe
					.xcall("pharmacy.overrides.po_dispatch.acknowledge_po", {
						purchase_order: frm.doc.name,
						...values,
					})
					.then(() => frm.reload_doc());
			},
			__("Record Supplier Acknowledgement"),
			__("Save")
		);
	}, __("Supplier"));
}
