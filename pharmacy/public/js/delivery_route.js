// Delivery Route — preview which stores have items due on a date

frappe.ui.form.on("Delivery Route", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Route Day"), () => {
			frappe.prompt({ fieldname: "date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today(), reqd: 1 },
				(v) => frm.call({ method: "get_route_day", doc: frm.doc, args: { date: v.date } }).then((r) => {
					const rows = r.message || [];
					frappe.msgprint({
						title: __("Stores with items due on {0}", [frappe.datetime.str_to_user(v.date)]),
						message: rows.length
							? `<table class="table table-sm"><tr><th>#</th><th>${__("Store")}</th><th>${__("Indents")}</th><th>${__("Lines")}</th></tr>${rows
								.map((s) => `<tr><td>${s.sequence}</td><td>${frappe.utils.escape_html(s.store)}</td><td>${s.indents}</td><td>${s.lines}</td></tr>`).join("")}</table>`
							: __("No store on this route has items due."),
					});
				}), __("Route Day"), __("Show"));
		});
	},
});
