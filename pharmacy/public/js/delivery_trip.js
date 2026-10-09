// Delivery Trip — a stop's customer and address come from its Delivery Note (or the customer's saved address)

frappe.ui.form.on("Delivery Stop", {
	delivery_note(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.delivery_note) return;
		frappe.xcall("pharmacy.overrides.delivery_trip.get_stop_details", { delivery_note: row.delivery_note }).then((d) => {
			if (d.customer && row.customer !== d.customer) frappe.model.set_value(cdt, cdn, "customer", d.customer);
			// set after the customer, whose own handler may clear the address
			setTimeout(() => {
				if (d.address) frappe.model.set_value(cdt, cdn, "address", d.address);
				if (d.contact) frappe.model.set_value(cdt, cdn, "contact", d.contact);
			}, 300);
		});
	},
	customer(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.customer || row.delivery_note) return;
		// ERPNext only looks for an address marked Shipping; fall back to the customer's other addresses
		setTimeout(() => {
			if (locals[cdt][cdn].address) return;
			frappe.xcall("pharmacy.overrides.delivery_trip.get_stop_details", { customer: row.customer }).then((d) => {
				if (d.address) frappe.model.set_value(cdt, cdn, "address", d.address);
			});
		}, 500);
	},
});

// one "Delivered" button per stop still to visit, so riders don't have to open the row to tick Visited
frappe.ui.form.on("Delivery Trip", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.has_perm("write")) return;
		(frm.doc.delivery_stops || []).filter((s) => !s.visited).forEach((s) => {
			const label = `#${s.idx} ${s.customer || ""}${s.delivery_note ? " · " + s.delivery_note : ""}`;
			frm.add_custom_button(label, () =>
				frappe.confirm(__("Mark stop {0} as delivered?", [label]), () =>
					frappe.xcall("pharmacy.overrides.delivery_trip.mark_stop_delivered", { delivery_trip: frm.doc.name, stop: s.name })
						.then(() => { frappe.show_alert({ message: __("Delivered"), indicator: "green" }); frm.reload_doc(); })),
				__("Mark Delivered"));
		});
		if ((frm.doc.delivery_stops || []).some((s) => !s.visited)) frm.page.set_inner_btn_group_as_primary(__("Mark Delivered"));
	},
});
