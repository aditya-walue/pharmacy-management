import frappe
from frappe import _


def validate_inward_batches(doc, method=None):
	"""No batch may come into stock without MRP and expiry.

	Runs on submit, after ERPNext has built the voucher's batch bundles, so batches it
	auto-creates during the receipt are covered too.
	"""
	bundle = frappe.qb.DocType("Serial and Batch Bundle")
	entry = frappe.qb.DocType("Serial and Batch Entry")
	batch = frappe.qb.DocType("Batch")

	missing = (
		frappe.qb.from_(entry)
		.join(bundle)
		.on(entry.parent == bundle.name)
		.join(batch)
		.on(batch.name == entry.batch_no)
		.select(batch.name)
		.distinct()
		.where(
			(bundle.voucher_type == doc.doctype)
			& (bundle.voucher_no == doc.name)
			& (bundle.type_of_transaction == "Inward")
			& (bundle.is_cancelled == 0)
			& (batch.nir_mrp.isnull() | (batch.nir_mrp == 0) | batch.expiry_date.isnull())
		)
		.run(pluck=True)
	)

	if missing:
		frappe.throw(
			_("Enter MRP and Expiry Date on these batches before receiving stock: {0}").format(
				", ".join(missing)
			),
			title=_("Batch details missing"),
		)
