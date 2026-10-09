import frappe

# 12% and 28% slabs were removed from 22 September 2025; India Compliance still creates them
RETIRED_GST_RATES = (12, 28)


def disable_if_retired(doc, method=None):
	if doc.gst_rate in RETIRED_GST_RATES and not doc.disabled:
		doc.db_set("disabled", 1)


def fix_zero_tax_on_validate(doc, method=None):
	if doc.get("gst_treatment") == "Taxable" and not doc.get("gst_rate"):
		if doc.taxes:
			for t in doc.taxes:
				if not t.tax_rate:
					t.tax_rate = 18.0
			doc.gst_rate = sum(t.tax_rate for t in doc.taxes)
		else:
			doc.gst_treatment = "Nil Rated"


def disable_retired_gst_templates():
	frappe.db.set_value(
		"Item Tax Template",
		{"gst_rate": ("in", RETIRED_GST_RATES), "disabled": 0},
		"disabled",
		1,
	)
