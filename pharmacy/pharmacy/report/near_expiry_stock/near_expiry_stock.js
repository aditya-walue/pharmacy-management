// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Near Expiry Stock"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "warehouse", label: __("Warehouse / Site"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "within_days", label: __("Expiring Within (Days)"), fieldtype: "Int", default: 180 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_to_expiry" && data && data.days_to_expiry <= 30) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
