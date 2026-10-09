// Copyright (c) 2026, Aditya and contributors
// For license information, please see license.txt

frappe.query_reports["Stock by Location"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "warehouse", label: __("Warehouse / Site"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "zone_type", label: __("Zone"), fieldtype: "Select", options: "\nReceiving\nGeneral\nCold Room\nScheduled Drug Cage\nFMCG\nQuarantine\nReturns\nExpired" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "regulatory_category", label: __("Category"), fieldtype: "Select", options: "\nOTC\nSchedule H\nSchedule H1\nSchedule X\nNDPS\nCosmetic\nFSSAI" },
		{ fieldname: "expiring_within", label: __("Expiring Within (Days)"), fieldtype: "Int" },
		{ fieldname: "group_by", label: __("Show"), fieldtype: "Select", options: "Batch\nBin\nZone\nSite\nItem", default: "Batch" },
	],
};
