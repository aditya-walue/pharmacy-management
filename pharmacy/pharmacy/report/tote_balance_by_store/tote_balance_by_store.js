// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Tote Balance by Store"] = {
	filters: [
		{ fieldname: "store", label: __("Store"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "from_date", label: __("Movements From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("Movements To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
