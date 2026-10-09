// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Slow and Non-Moving Stock"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "warehouse", label: __("Warehouse / Site"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "period_days", label: __("Movement Period (Days)"), fieldtype: "Int", default: 90 },
		{ fieldname: "non_moving_days", label: __("Non-Moving After (Days)"), fieldtype: "Int", default: 180 },
		{ fieldname: "slow_cover_days", label: __("Slow if Cover Above (Days)"), fieldtype: "Int", default: 90 },
		{ fieldname: "show", label: __("Show"), fieldtype: "Select", options: "Slow and Non-Moving\nAll", default: "Slow and Non-Moving" },
	],
};
