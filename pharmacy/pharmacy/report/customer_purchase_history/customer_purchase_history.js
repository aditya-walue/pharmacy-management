// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Purchase History"] = {
	filters: [
		{ fieldname: "mobile", label: __("Mobile"), fieldtype: "Data" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -12) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
