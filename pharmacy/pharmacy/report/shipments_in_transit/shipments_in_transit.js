// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Shipments in Transit"] = {
	filters: [{ fieldname: "store", label: __("Store"), fieldtype: "Link", options: "Warehouse" }],
	onload(report) {
		report.page.add_inner_button(__("Receive Selected"), () => {
			const row = report.datatable && report.datatable.rowmanager.getCheckedRows().map((i) => report.data[i])[0];
			if (!row) return frappe.msgprint(__("Tick a shipment row first."));
			frappe.xcall("pharmacy.pharmacy.doctype.store_receipt.store_receipt.create_store_receipt",
				{ dispatch_doctype: row.document_type, dispatch_name: row.shipment })
				.then((name) => frappe.set_route("Form", "Store Receipt", name));
		});
	},
	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},
};
