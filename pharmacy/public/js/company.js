// Company — load the pharmacy demo data (items, DC, stores, stock, POS, online orders) for this company

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.country !== "India" || !frappe.user.has_role("System Manager")) return;
		frm.add_custom_button(__("Load Pharmacy Demo Data"), () =>
			frappe.confirm(
				__("Load the pharmacy demo data for {0}? It adds test items (including a batch + serial numbered glucometer), a DC with bins, two stores, suppliers, licences, opening stock, store sales, POS and online-order setup. It runs in the background.", [frm.doc.name]),
				() => frappe.xcall("pharmacy.demo_data.load_demo_data", { company: frm.doc.name }).then((msg) => frappe.msgprint(msg))
			), __("Pharmacy"));
	},
});
