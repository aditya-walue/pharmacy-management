// Sales Order — online orders: pharmacist prescription check, bill per location, delivery

const ONLINE = "pharmacy.online.fulfilment";

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (!frm.doc.nir_is_online_order || frm.is_new()) return;
		const status = frm.doc.nir_online_status;
		const colour = { Cart: "gray", "Prescription Review": "orange", "Awaiting Payment": "orange", Confirmed: "blue",
			"Partly Dispatched": "blue", Dispatched: "blue", Delivered: "green", Cancelled: "red", Rejected: "red" }[status];
		frm.dashboard.set_headline(__("Online order: {0} · {1} · Payment {2}", [__(status), __(frm.doc.nir_fulfilment_type),
			__(frm.doc.nir_payment_status || "")]), colour);

		if (frm.doc.nir_prescription) {
			frm.add_custom_button(__("View Prescription"), () => window.open(frm.doc.nir_prescription), __("Prescription"));
		}

		(frm.doc.nir_fulfilments || []).forEach((row) => {
			const where = row.pharmacy_store || row.warehouse;
			const call = (method, args = {}) => frappe.xcall(`${ONLINE}.${method}`, { sales_order: frm.doc.name, warehouse: row.warehouse, ...args });
			if (["Confirmed", "Partly Dispatched"].includes(status) && ["Allocated", "Awaiting Transfer"].includes(row.status) && !row.sales_invoice) {
				frm.add_custom_button(where, () => call("make_invoice").then((si) => frappe.set_route("Form", "Sales Invoice", si)), __("Bill"));
			}
			if (row.status === "Billed") {
				frm.add_custom_button(__("{0}: Out for Delivery", [where]), () => call("mark_out_for_delivery").then(() => frm.reload_doc()), __("Delivery"));
			}
			if (["Billed", "Out for Delivery", "Ready for Pickup"].includes(row.status)) {
				const label = row.status === "Ready for Pickup" ? __("{0}: Picked Up", [where]) : __("{0}: Delivered", [where]);
				frm.add_custom_button(label, () => delivered(frm, call), __("Delivery"));
			}
		});
	},
});

function approve(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Approve Prescription"),
		fields: [
			{ fieldtype: "HTML", options: frm.doc.nir_prescription ? `<a href="${frm.doc.nir_prescription}" target="_blank">${__("Open prescription")}</a>` : "" },
			{ fieldname: "doctor_name", label: __("Doctor Name"), fieldtype: "Data", reqd: 1, default: frm.doc.nir_doctor_name },
			{ fieldname: "doctor_reg_no", label: __("Doctor Registration No"), fieldtype: "Data", reqd: 1, default: frm.doc.nir_doctor_reg_no },
			{ fieldname: "patient_name", label: __("Patient Name"), fieldtype: "Data", default: frm.doc.nir_online_patient_name },
			{ fieldname: "valid_upto", label: __("Prescription Valid Upto"), fieldtype: "Date" },
			{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
		],
		primary_action_label: __("Approve and Release"),
		primary_action(values) {
			frappe.xcall(`${ONLINE}.approve_prescription`, { sales_order: frm.doc.name, ...values }).then(() => { d.hide(); frm.reload_doc(); });
		},
	});
	d.show();
}

function reject(frm) {
	frappe.prompt({ fieldname: "remarks", label: __("Reason (sent to the customer)"), fieldtype: "Small Text", reqd: 1 },
		(v) => frappe.xcall(`${ONLINE}.reject_prescription`, { sales_order: frm.doc.name, remarks: v.remarks }).then(() => frm.reload_doc()),
		__("Reject Prescription"));
}

function delivered(frm, call) {
	if (frm.doc.nir_payment_method !== "Cash on Delivery") return call("mark_delivered").then(() => frm.reload_doc());
	frappe.prompt({ fieldname: "cod_amount", label: __("Cash Collected"), fieldtype: "Currency", reqd: 1 },
		(v) => call("mark_delivered", { cod_amount: v.cod_amount }).then(() => frm.reload_doc()), __("Cash on Delivery"));
}
