import frappe
from frappe import _

from pharmacy.overrides.po_dispatch import get_suppliers_for_user

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?" + frappe.utils.urlencode(
			{"redirect-to": frappe.request.full_path}
		)
		raise frappe.Redirect

	suppliers = get_suppliers_for_user()
	if not suppliers:
		frappe.throw(_("This page is for supplier portal users only"), frappe.PermissionError)

	context.show_sidebar = True
	context.title = _("Purchase Order Acknowledgement")

	name = frappe.form_dict.get("name")
	if name:
		doc = frappe.get_doc("Purchase Order", name)
		if doc.supplier not in suppliers or doc.docstatus != 1:
			frappe.throw(_("Purchase Order {0} not found").format(name), frappe.PermissionError)
		context.doc = doc
		context.is_open = doc.status not in ("Closed", "Completed", "Cancelled")
		return

	context.orders = frappe.get_all(
		"Purchase Order",
		filters={
			"supplier": ("in", suppliers),
			"docstatus": 1,
			"status": ("not in", ("Closed", "Completed", "Cancelled")),
		},
		fields=[
			"name",
			"transaction_date",
			"grand_total",
			"currency",
			"nir_po_email_status",
			"nir_expected_delivery_date",
		],
		order_by="transaction_date desc",
	)
