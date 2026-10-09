frappe.listview_settings["Pick Wave"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Create Today's Waves"), () => {
			frappe.prompt(
				[
					{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), reqd: 1,
						default: frappe.defaults.get_user_default("Company") },
					{ fieldname: "source_warehouse", fieldtype: "Link", options: "Warehouse", label: __("DC"), reqd: 1 },
				],
				(v) => frappe.xcall("pharmacy.pharmacy.doctype.pick_wave.pick_wave.create_waves", v).then((waves) => {
					frappe.msgprint(waves.length ? __("Created {0}", [waves.join(", ")]) : __("No due indents for any route."));
					listview.refresh();
				}),
				__("Create Pick Waves"),
				__("Create")
			);
		});
	},
};
