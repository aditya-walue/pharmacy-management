// Purchase Receipt (GRN) — gate entry, Scan & Receive, and MRP change approval

frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		frm.set_query("nir_gate_entry", () => ({
			filters: { docstatus: 1, supplier: frm.doc.supplier, company: frm.doc.company, status: ["!=", "Cancelled"] },
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.is_return) return;

		frm.add_custom_button(__("Scan & Receive"), () => scan_and_receive(frm));

		if (frm.doc.nir_mrp_change_pending && !frm.is_dirty() && frappe.user.has_role("Category Manager")
			&& frappe.session.user !== frm.doc.owner) {
			frm.add_custom_button(__("Approve MRP Changes"), () => {
				frappe
					.xcall("pharmacy.overrides.inbound.approve_mrp_change", { purchase_receipt: frm.doc.name })
					.then(() => frm.reload_doc());
			});
		}
	},
});

function scan_and_receive(frm) {
	if (!frm.doc.supplier || !frm.doc.nir_gate_entry) {
		frappe.msgprint(__("Select the Supplier and Gate Entry first."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Scan & Receive"),
		fields: [
			{ fieldname: "barcode", fieldtype: "Data", label: __("Scan Barcode"), reqd: 1 },
			{ fieldname: "item_info", fieldtype: "HTML" },
			{ fieldname: "col1", fieldtype: "Column Break" },
			{ fieldname: "qty", fieldtype: "Float", label: __("Qty Received"), reqd: 1, default: 1 },
			{ fieldname: "free_qty", fieldtype: "Float", label: __("Free Qty") },
			{ fieldname: "invoiced_qty", fieldtype: "Float", label: __("Qty as per Invoice") },
			{ fieldname: "sec_batch", fieldtype: "Section Break", label: __("Batch") },
			{ fieldname: "supplier_batch_no", fieldtype: "Data", label: __("Supplier Batch No"), reqd: 1 },
			{ fieldname: "mfg_date", fieldtype: "Date", label: __("Mfg Date") },
			{ fieldname: "col2", fieldtype: "Column Break" },
			{ fieldname: "expiry_date", fieldtype: "Date", label: __("Expiry Date"), reqd: 1 },
			{ fieldname: "mrp", fieldtype: "Currency", label: __("MRP (per pack)"), reqd: 1 },
			{ fieldname: "sec_cold", fieldtype: "Section Break", label: __("Cold Chain"), depends_on: "eval:doc.cold_chain" },
			{ fieldname: "cold_chain", fieldtype: "Check", hidden: 1 },
			{ fieldname: "temperature", fieldtype: "Data", label: __("Temperature (°C)") },
			{ fieldname: "col3", fieldtype: "Column Break" },
			{
				fieldname: "logger_status",
				fieldtype: "Select",
				label: __("Data Logger"),
				options: ["", "OK", "Excursion", "Not Available"].join("\n"),
			},
		],
		primary_action_label: __("Add Line"),
		primary_action(values) {
			const scanned = dialog.scanned;
			if (!scanned || scanned.barcode !== values.barcode) {
				frappe.msgprint(__("Press Enter in the barcode field to look the item up first."));
				return;
			}
			add_line(frm, scanned.details, values);
			// stay open for the next scan
			dialog.clear();
			dialog.scanned = null;
			dialog.fields_dict.item_info.$wrapper.empty();
			dialog.fields_dict.barcode.set_focus();
		},
	});

	dialog.fields_dict.barcode.$input.on("change", () => {
		const barcode = (dialog.get_value("barcode") || "").trim();
		if (!barcode) return;
		frappe
			.xcall("pharmacy.overrides.inbound.resolve_scan", {
				barcode,
				supplier: frm.doc.supplier,
				company: frm.doc.company,
			})
			.then((details) => {
				dialog.scanned = { barcode, details };
				dialog.set_value("cold_chain", details.cold_chain ? 1 : 0);
				const po = details.purchase_order
					? __("PO {0}: {1} {2} pending", [details.purchase_order, details.pending_qty, details.uom])
					: `<span class="text-danger">${__("Not on any open PO from this supplier")}</span>`;
				dialog.fields_dict.item_info.$wrapper.html(
					`<div class="small"><b>${frappe.utils.escape_html(details.item_name)}</b><br>${po}</div>`
				);
				dialog.fields_dict.qty.set_focus();
			});
	});

	dialog.show();
	dialog.fields_dict.barcode.set_focus();
}

function add_line(frm, details, values) {
	const row = frm.add_child("items", {
		item_code: details.item_code,
		item_name: details.item_name,
		uom: details.uom,
		conversion_factor: details.conversion_factor,
		qty: values.qty,
		received_qty: values.qty,
		rate: details.rate,
		warehouse: details.warehouse || frm.doc.set_warehouse,
		purchase_order: details.purchase_order,
		purchase_order_item: details.purchase_order_item,
		nir_supplier_batch_no: values.supplier_batch_no,
		nir_mfg_date: values.mfg_date,
		nir_expiry_date: values.expiry_date,
		nir_mrp: values.mrp,
		nir_free_qty: values.free_qty,
		nir_invoiced_qty: values.invoiced_qty,
		nir_temperature: values.temperature,
		nir_logger_status: values.logger_status,
	});
	frm.refresh_field("items");
	frappe.show_alert({ message: __("Added {0} x {1}", [values.qty, details.item_name]), indicator: "green" });
	return row;
}

// Batch No fills itself once the supplier batch, expiry and MRP are on the line
frappe.ui.form.on("Purchase Receipt Item", {
	nir_supplier_batch_no: fill_batch,
	nir_expiry_date: fill_batch,
	nir_mrp: fill_batch,
	nir_mfg_date: fill_batch,
});

function fill_batch(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !row.nir_supplier_batch_no || !row.nir_expiry_date || !row.nir_mrp) return;
	frappe
		.xcall("pharmacy.overrides.inbound.create_line_batch", {
			item_code: row.item_code, supplier_batch_no: row.nir_supplier_batch_no, expiry_date: row.nir_expiry_date,
			mfg_date: row.nir_mfg_date, mrp: row.nir_mrp, uom: row.uom, supplier: frm.doc.supplier,
		})
		.then((batch) => {
			if (!batch) return;
			frappe.model.set_value(cdt, cdn, "use_serial_batch_fields", 1);
			frappe.model.set_value(cdt, cdn, "batch_no", batch);
		});
}
