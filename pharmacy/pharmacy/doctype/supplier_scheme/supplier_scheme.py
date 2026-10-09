# Copyright (c) 2026, Aditya and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class SupplierScheme(Document):
    def validate(self):
        if self.valid_from and self.valid_upto and self.valid_from > self.valid_upto:
            frappe.throw(_("Valid From cannot be after Valid Upto."), title=_("Invalid Dates"))

        if self.scheme_type in ("Quantity Discount", "Cash Discount") and not self.discount_pct:
            frappe.throw(
                _("Discount % is required for {0} scheme type.").format(self.scheme_type),
                title=_("Missing Benefit"),
            )

        if self.scheme_type == "Free Goods" and not self.free_goods_ratio:
            frappe.throw(
                _("Free Goods Ratio is required for Free Goods scheme type."),
                title=_("Missing Benefit"),
            )
