// Dispatch Trip — fetch dispatches, scan-load totes, depart, deliver stops, collect empties

const TRIP = "pharmacy.pharmacy.doctype.dispatch_trip.dispatch_trip";

frappe.ui.form.on("Dispatch Trip", {
	vehicle(frm) {
		if (frm.doc.vehicle) {
			frappe.db.get_value("Vehicle", frm.doc.vehicle, "license_plate").then((r) =>
				frm.set_value("vehicle_no", (r.message && r.message.license_plate) || frm.doc.vehicle));
		}
	},
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		const s = frm.doc.status;
		if (s === "Planned") {
			frm.add_custom_button(__("Get Dispatches"), () =>
				frm.call({ method: "get_dispatches", doc: frm.doc, freeze: true }).then(() => frm.reload_doc()));
		}
		if (["Planned", "Loading"].includes(s) && (frm.doc.totes || []).length) {
			frm.add_custom_button(__("Scan Load"), () => scan_loop(frm, __("Scan Tote onto Vehicle"), (tote) =>
				frappe.xcall(`${TRIP}.load_scan`, { trip: frm.doc.name, tote }).then((r) => __("Loaded {0} of {1}", [r.loaded, r.of])))).addClass("btn-primary");
			frm.add_custom_button(__("Depart"), () =>
				frappe.xcall(`${TRIP}.depart`, { trip: frm.doc.name }).then(() => frm.reload_doc()));
		}
		if (s === "Departed") {
			frm.add_custom_button(__("Deliver Stop"), () => {
				const open = (frm.doc.stops || []).filter((r) => r.status !== "Delivered");
				frappe.prompt([
					{ fieldname: "stop", fieldtype: "Select", label: __("Stop"), reqd: 1,
						options: open.map((r) => ({ value: r.name, label: `${r.sequence}. ${r.store_warehouse}` })) },
					{ fieldname: "received_by", fieldtype: "Data", label: __("Received By"), reqd: 1 },
				], (v) => frappe.xcall(`${TRIP}.deliver_stop`, { trip: frm.doc.name, ...v }).then(() => frm.reload_doc()),
				__("Deliver Stop"), __("Delivered"));
			});
			frm.add_custom_button(__("Complete Trip"), () =>
				frappe.xcall(`${TRIP}.complete`, { trip: frm.doc.name }).then(() => frm.reload_doc()));
		}
		if (["Departed", "Completed"].includes(s)) {
			frm.add_custom_button(__("Collect Empties"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Scan Returned Totes / Crates / Ice Boxes"),
					fields: [
						{ fieldname: "condition", fieldtype: "Select", label: __("Condition"), options: "Good\nDamaged", default: "Good" },
						{ fieldname: "tote", fieldtype: "Data", label: __("Scan Tote") },
						{ fieldname: "last", fieldtype: "HTML" },
					],
				});
				d.fields_dict.tote.$input.on("change", () => {
					const tote = (d.get_value("tote") || "").trim();
					if (!tote) return;
					frappe.xcall(`${TRIP}.return_scan`, { trip: frm.doc.name, tote, condition: d.get_value("condition") })
						.then((r) => d.fields_dict.last.$wrapper.html(`<div class="small text-success">${__("{0} returned ({1} on this trip)", [tote, r.returned])}</div>`))
						.finally(() => { d.set_value("tote", ""); d.fields_dict.tote.set_focus(); frm.reload_doc(); });
				});
				d.show();
				d.fields_dict.tote.set_focus();
			});
		}
	},
});

function scan_loop(frm, label, action) {
	const d = new frappe.ui.Dialog({ title: label, fields: [{ fieldname: "tote", fieldtype: "Data", label: __("Tote") }, { fieldname: "last", fieldtype: "HTML" }] });
	d.fields_dict.tote.$input.on("change", () => {
		const tote = (d.get_value("tote") || "").trim();
		if (!tote) return;
		action(tote)
			.then((msg) => d.fields_dict.last.$wrapper.html(`<div class="small text-success">${msg}</div>`))
			.finally(() => { d.set_value("tote", ""); d.fields_dict.tote.set_focus(); frm.reload_doc(); });
	});
	d.show();
	d.fields_dict.tote.set_focus();
}
