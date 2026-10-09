// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Schedule H1 Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "warehouse", label: __("Store"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
	],
};
