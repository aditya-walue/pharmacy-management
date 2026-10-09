// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Store Stock Overview"] = {
	filters: [
		{ fieldname: "store", label: __("Store"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "sales_days", label: __("Sales Period (Days)"), fieldtype: "Int", default: 30 },
	],
};
