"""Purchase Orders are raised per warehouse and supplier and approved through the PO Approval Matrix."""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, now_datetime
from frappe.utils.nestedset import get_descendants_of
from frappe.utils.user import get_users_with_role

from pharmacy.overrides.rate_contract import get_variance_items

# who signs off a line priced above its rate contract
CONTRACT_VARIANCE_ROLE = "Category Manager"


def validate_purchase_order(doc, method=None):
	validate_single_warehouse(doc)
	update_approvals(doc)


def validate_single_warehouse(doc):
	"""One PO per warehouse and supplier, so every line must go to the same warehouse."""
	warehouses = {row.warehouse or doc.set_warehouse for row in doc.items} - {None, ""}
	if len(warehouses) > 1:
		frappe.throw(
			_("A Purchase Order can be raised for one warehouse only. This one has lines for: {0}").format(
				", ".join(sorted(warehouses))
			),
			title=_("Multiple warehouses"),
		)

	if warehouses and not doc.set_warehouse:
		doc.set_warehouse = warehouses.pop()


def update_approvals(doc):
	"""Rebuild the approval table whenever what needs approving changes; otherwise keep its progress."""
	requirements = get_required_approvals(doc)
	signature = get_signature(doc, requirements)

	# a maker's re-save after rejection asks for approval again
	resubmitted = doc.nir_approval_status == "Rejected" and not doc.flags.nir_approval_action
	if signature != doc.nir_approval_signature or resubmitted:
		doc.set(
			"nir_approvals",
			[{**requirement, "status": "Pending"} for requirement in requirements],
		)
		doc.nir_approval_signature = signature
		doc.flags.nir_notify_approvers = bool(requirements)

	doc.nir_approval_status = get_overall_status(doc)


def get_required_approvals(doc):
	"""Matrix rules matching the PO's company, warehouse and value, per category where a rule is category-specific."""
	rules = frappe.get_all(
		"PO Approval Matrix",
		filters={"company": doc.company, "disabled": 0},
		fields=[
			"name",
			"warehouse",
			"applies_to",
			"regulatory_category",
			"item_group",
			"from_value",
			"to_value",
			"approval_level",
			"approver_role",
		],
		order_by="approval_level asc, from_value asc",
	)
	lines = get_line_values(doc)
	required = {}

	if variance_items := get_variance_items(doc):
		required[(1, CONTRACT_VARIANCE_ROLE)] = {
			"approval_level": 1,
			"approver_role": CONTRACT_VARIANCE_ROLE,
			"basis": _("Above contract rate: {0}").format(", ".join(sorted(set(variance_items)))),
			"rule": None,
		}
	for rule in rules:
		if rule.warehouse and not warehouse_in(doc.set_warehouse, rule.warehouse):
			continue

		value, basis = get_rule_value(rule, lines, doc)
		if value <= 0 or value < flt(rule.from_value):
			continue
		if flt(rule.to_value) and value > flt(rule.to_value):
			continue

		# the same role at the same level approves once, however many rules ask for it
		key = (rule.approval_level, rule.approver_role)
		required.setdefault(
			key,
			{
				"approval_level": rule.approval_level,
				"approver_role": rule.approver_role,
				"basis": basis,
				"rule": rule.name,
			},
		)

	return sorted(required.values(), key=lambda r: (r["approval_level"], r["approver_role"]))


def get_line_values(doc):
	item_codes = list({row.item_code for row in doc.items if row.item_code})
	categories = dict(
		frappe.get_all(
			"Item",
			filters={"name": ("in", item_codes)},
			fields=["name", "nir_regulatory_category"],
			as_list=True,
		)
	)
	return [
		frappe._dict(
			value=flt(row.base_net_amount) or flt(row.base_amount) or flt(row.amount),
			item_group=row.item_group,
			category=categories.get(row.item_code),
		)
		for row in doc.items
	]


def get_rule_value(rule, lines, doc):
	currency = frappe.get_cached_value("Company", doc.company, "default_currency")

	if rule.applies_to == "Regulatory Category":
		value = sum(line.value for line in lines if line.category == rule.regulatory_category)
		label = rule.regulatory_category
	elif rule.applies_to == "Item Group":
		groups = {rule.item_group, *get_descendants_of("Item Group", rule.item_group)}
		value = sum(line.value for line in lines if line.item_group in groups)
		label = rule.item_group
	else:
		value = flt(doc.base_net_total) or sum(line.value for line in lines)
		label = _("PO value")

	return value, f"{label}: {fmt_money(value, currency=currency)}"


def warehouse_in(warehouse, parent):
	if not warehouse:
		return False
	if warehouse == parent:
		return True

	lft, rgt = frappe.get_cached_value("Warehouse", parent, ["lft", "rgt"])
	return bool(
		frappe.db.exists("Warehouse", {"name": warehouse, "lft": (">", lft), "rgt": ("<", rgt)})
	)


def get_signature(doc, requirements):
	"""Changes to supplier, warehouse, lines or the approvers needed invalidate earlier approvals."""
	payload = {
		"supplier": doc.supplier,
		"warehouse": doc.set_warehouse,
		"lines": sorted((row.item_code, flt(row.qty), flt(row.rate)) for row in doc.items),
		"requirements": [(r["approval_level"], r["approver_role"]) for r in requirements],
	}
	return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def get_overall_status(doc):
	statuses = {row.status for row in doc.nir_approvals}
	if not statuses:
		return "Not Required"
	if "Rejected" in statuses:
		return "Rejected"
	if statuses == {"Approved"}:
		return "Approved"
	return "Pending"


def get_current_level_rows(doc):
	pending = [row for row in doc.nir_approvals if row.status == "Pending"]
	if not pending:
		return []
	level = min(row.approval_level for row in pending)
	return [row for row in pending if row.approval_level == level]


def validate_approved(doc, method=None):
	if doc.nir_approval_status in ("Not Required", "Approved"):
		return

	if doc.nir_approval_status == "Rejected":
		frappe.throw(_("This Purchase Order was rejected. Edit and save it to request approval again."))

	waiting = ", ".join(f"{_('Level')} {row.approval_level}: {row.approver_role}" for row in get_current_level_rows(doc))
	frappe.throw(
		_("This Purchase Order needs approval before it can be submitted. Waiting for {0}").format(waiting),
		title=_("Approval pending"),
	)


def notify_approvers(doc, method=None):
	if not doc.flags.nir_notify_approvers:
		return
	doc.flags.nir_notify_approvers = False

	rows = get_current_level_rows(doc)
	users = {user for row in rows for user in get_users_with_role(row.approver_role)} - {doc.owner}
	subject = _("Purchase Order {0} for {1} ({2}) is waiting for your approval").format(
		doc.name, doc.supplier, fmt_money(doc.grand_total, currency=doc.currency)
	)
	for user in users:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"subject": subject,
			}
		).insert(ignore_permissions=True)


@frappe.whitelist()
def get_actionable_rows(purchase_order: str) -> list[str]:
	"""Names of approval rows the current user may approve or reject right now."""
	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("read")
	return [row.name for row in get_user_rows(doc)]


def get_user_rows(doc):
	user = frappe.session.user
	if doc.docstatus != 0 or user == doc.owner:
		return []

	roles = set(frappe.get_roles(user))
	return [row for row in get_current_level_rows(doc) if row.approver_role in roles]


@frappe.whitelist()
def act_on_purchase_order(purchase_order: str, action: str, remarks: str | None = None):
	"""Approve or reject the current level for every role the user holds. The PO's maker cannot act."""
	if action not in ("Approve", "Reject"):
		frappe.throw(_("Invalid action {0}").format(action))

	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("read")

	if frappe.session.user == doc.owner:
		frappe.throw(_("You raised this Purchase Order, so someone else must approve it."))

	rows = get_user_rows(doc)
	if not rows:
		frappe.throw(_("Nothing on this Purchase Order is waiting for your approval."))

	if action == "Reject" and not remarks:
		frappe.throw(_("Give a reason for rejecting."))

	status = "Approved" if action == "Approve" else "Rejected"
	for row in rows:
		row.status = status
		row.approved_by = frappe.session.user
		row.approved_on = now_datetime()
		row.remarks = remarks

	# approvers may not have write access to the PO; their action is authorised by the role check above
	doc.flags.ignore_permissions = True
	doc.flags.nir_approval_action = True
	doc.flags.nir_notify_approvers = status == "Approved"
	doc.save()

	doc.add_comment(
		"Comment",
		_("{0} level {1} ({2}){3}").format(
			status,
			rows[0].approval_level,
			", ".join(row.approver_role for row in rows),
			f": {remarks}" if remarks else "",
		),
	)
	return doc.nir_approval_status
