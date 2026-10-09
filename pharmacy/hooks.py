app_name = "pharmacy"
app_title = "pharmacy"
app_publisher = "Aditya"
app_description = "pharmacy"
app_email = "Aditya@walue.biz"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext", "india_compliance"]

# Fixtures
# ------------------

fixtures = [
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"Category Manager",
					"Buyer",
					"Warehouse Manager",
					"Inward QC Executive",
					"Picker Packer",
					"Dispatch Coordinator",
					"Delivery Rider",
					"Store Pharmacist",
					"Online Order Pharmacist",
					"E-commerce Manager",
					"Customer Support",
					"Area Manager",
					"Pharmacy Accounts",
					"Compliance Pharmacist",
					"Pharmacy Management",
				],
			]
		],
	}
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pharmacy",
# 		"logo": "/assets/pharmacy/logo.png",
# 		"title": "pharmacy",
# 		"route": "/pharmacy",
# 		"has_permission": "pharmacy.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pharmacy/css/pharmacy.css"
# app_include_js = "/assets/pharmacy/js/pharmacy.js"

# include js, css files in header of web template
# web_include_css = "/assets/pharmacy/css/pharmacy.css"
# web_include_js = "/assets/pharmacy/js/pharmacy.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pharmacy/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Purchase Suggestion": "public/js/purchase_suggestion.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Put-away List": "public/js/put_away_list.js",
	"Stock Entry": "public/js/stock_adjustment.js",
	"Stock Reconciliation": "public/js/stock_adjustment.js",
	"Stock Count": "public/js/stock_count.js",
	"Stock Hold": "public/js/stock_hold.js",
	"Pick Wave": "public/js/pick_wave.js",
	"Delivery Route": "public/js/delivery_route.js",
	"Dispatch Trip": "public/js/dispatch_trip.js",
	"Tote": "public/js/tote.js",
	"Store Receipt": "public/js/store_receipt.js",
	"Transfer Discrepancy": "public/js/transfer_discrepancy.js",
	"Store Transfer Request": "public/js/store_transfer_request.js",
	"POS Invoice": "public/js/store_bill.js",
	"Gate Entry": "public/js/gate_entry.js",
	"Customer": "public/js/customer.js",
	"Sales Order": "public/js/online_sales_order.js",
	"Sales Invoice": "public/js/store_bill.js",
}

# pharmacy search (salt / brand / barcode, batches, expiry, MRP, loose units) on ERPNext's POS screen
page_js = {"point-of-sale": "public/js/pos_pharmacy.js"}
doctype_list_js = {"Pick Wave": "public/js/pick_wave_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pharmacy/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": ["pharmacy.utils.labels.barcode_img"],
}

# Installation
# ------------

# before_install = "pharmacy.install.before_install"
after_install = "pharmacy.install.after_install"
after_migrate = "pharmacy.install.after_migrate"
setup_wizard_complete = "pharmacy.install.setup_wizard_complete"

# Uninstallation
# ------------

# before_uninstall = "pharmacy.uninstall.before_uninstall"
# after_uninstall = "pharmacy.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pharmacy.utils.before_app_install"
# after_app_install = "pharmacy.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pharmacy.utils.before_app_uninstall"
# after_app_uninstall = "pharmacy.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "pharmacy.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pharmacy.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Payment Request": {
		"on_payment_authorized": "pharmacy.online.payment.on_payment_authorized",
	},
	"Batch": {
		"before_insert": "pharmacy.overrides.batch.set_batch_id",
		"validate": [
			"pharmacy.overrides.batch.validate_batch",
			"pharmacy.overrides.maker_checker.process_maker_checker",
		],
	},
	"Item": {
		"before_insert": "pharmacy.overrides.item.set_default_hsn_for_tests",
		"validate": [
			"pharmacy.overrides.item.validate_item",
			"pharmacy.overrides.maker_checker.process_maker_checker",
		],
	},
	"Supplier": {
		"validate": "pharmacy.overrides.maker_checker.process_maker_checker",
	},
	"Customer": {
		"validate": [
			"pharmacy.overrides.customer.validate_mobile",
			"pharmacy.overrides.maker_checker.process_maker_checker",
		],
	},
	"Item Price": {
		"validate": "pharmacy.overrides.maker_checker.process_maker_checker",
	},
	"Replenishment Schedule": {
		"validate": "pharmacy.overrides.maker_checker.process_maker_checker",
	},
	"Pharmacy Store": {
		"validate": "pharmacy.overrides.maker_checker.process_maker_checker",
	},
	"Item Tax Template": {
		"validate": "pharmacy.overrides.item_tax_template.fix_zero_tax_on_validate",
		"after_insert": "pharmacy.overrides.item_tax_template.disable_if_retired",
	},
	"Blanket Order": {
		"validate": "pharmacy.overrides.rate_contract.validate_blanket_order",
	},
	"Purchase Order": {
		"validate": [
			# prices first, so approvals see the final rates and any contract variance
			"pharmacy.overrides.rate_contract.apply_rate_contracts",
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.po_approval.validate_purchase_order",
		],
		"on_update": "pharmacy.overrides.po_approval.notify_approvers",
		"before_submit": "pharmacy.overrides.po_approval.validate_approved",
		"on_submit": [
			"pharmacy.overrides.patient_order.update_patient_so_tracking",
			"pharmacy.overrides.po_dispatch.send_on_submit",
		],
	},
	"Purchase Receipt": {
		"before_validate": "pharmacy.overrides.inbound.prepare_batches",
		"validate": [
			# first: it sets batches and may re-route cold-chain breaches to quarantine
			"pharmacy.overrides.inbound.validate_receipt",
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.storage.validate_storage",
		],
		"before_submit": [
			"pharmacy.overrides.inbound.validate_before_submit",
			"pharmacy.overrides.storage.validate_bin_capacity",
			"pharmacy.overrides.controlled_drugs.require_custodian",
		],
		"on_submit": [
			"pharmacy.overrides.stock_inward.validate_inward_batches",
			"pharmacy.overrides.shelf_life.validate_shelf_life",
			"pharmacy.overrides.patient_order.update_patient_so_tracking",
			"pharmacy.overrides.po_fulfilment.update_from_receipt",
			"pharmacy.overrides.inbound.on_submit",
			"pharmacy.overrides.putaway.make_putaway_list",
			"pharmacy.overrides.controlled_drugs.record_receipt",
		],
		"on_cancel": [
			"pharmacy.overrides.po_fulfilment.update_from_receipt",
			"pharmacy.overrides.inbound.on_cancel",
			"pharmacy.overrides.controlled_drugs.reverse_receipt",
		],
	},
	"Purchase Invoice": {
		"validate": [
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.storage.validate_storage",
		],
		"before_submit": [
			"pharmacy.overrides.storage.validate_bin_capacity",
			"pharmacy.overrides.three_way_match.validate_match",
		],
		"on_submit": [
			"pharmacy.overrides.stock_inward.validate_inward_batches",
			"pharmacy.overrides.shelf_life.validate_shelf_life",
			"pharmacy.overrides.po_fulfilment.update_from_receipt",
			"pharmacy.overrides.three_way_match.raise_debit_notes",
		],
		"on_cancel": "pharmacy.overrides.po_fulfilment.update_from_receipt",
	},
	"Sales Invoice": {
		"validate": [
			# first: sets batches the hold / quarantine checks below then look at
			"pharmacy.overrides.pos_billing.apply_pos_rules",
			"pharmacy.overrides.prescription.fill_from_saved_prescription",
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.quarantine.block_allocation",
			"pharmacy.overrides.stock_hold.block_held_allocation",
		],
		"before_submit": [
			"pharmacy.overrides.prescription.validate_prescription",
			"pharmacy.overrides.controlled_drugs.require_custodian",
			"pharmacy.overrides.pos_billing.require_discount_approval",
		],
		"on_submit": [
			"pharmacy.overrides.shelf_life.validate_shelf_life",
			"pharmacy.overrides.patient_order.update_patient_so_tracking",
			"pharmacy.overrides.prescription.save_prescription",
			"pharmacy.overrides.controlled_drugs.record_sale",
			"pharmacy.online.fulfilment.update_from_invoice",
		],
		"on_update": "pharmacy.overrides.pos_billing.notify_discount_approvers",
		"on_cancel": [
			"pharmacy.overrides.controlled_drugs.reverse_sale",
			"pharmacy.online.fulfilment.update_from_invoice",
		],
	},
	"POS Invoice": {
		"validate": [
			# first: sets batches the hold / quarantine checks below then look at
			"pharmacy.overrides.pos_billing.apply_pos_rules",
			"pharmacy.overrides.prescription.fill_from_saved_prescription",
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.quarantine.block_allocation",
			"pharmacy.overrides.stock_hold.block_held_allocation",
		],
		"before_submit": [
			"pharmacy.overrides.prescription.validate_prescription",
			"pharmacy.overrides.pos_billing.require_discount_approval",
		],
		"on_submit": [
			"pharmacy.overrides.patient_order.update_patient_so_tracking",
			"pharmacy.overrides.prescription.save_prescription",
			"pharmacy.overrides.controlled_drugs.record_sale",
		],
		"on_update": "pharmacy.overrides.pos_billing.notify_discount_approvers",
		"on_cancel": "pharmacy.overrides.controlled_drugs.reverse_sale",
	},
	"Delivery Note": {
		"validate": [
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.quarantine.block_allocation",
			"pharmacy.overrides.stock_hold.block_held_allocation",
		],
		"on_submit": "pharmacy.overrides.shelf_life.validate_shelf_life",
		"before_submit": "pharmacy.overrides.controlled_drugs.require_custodian",
	},
	"Stock Entry": {
		"validate": [
			"pharmacy.overrides.party_licence.validate_party_licence",
			"pharmacy.overrides.storage.validate_storage",
			"pharmacy.overrides.quarantine.block_stock_entry",
			"pharmacy.overrides.stock_adjustment.validate_adjustment",
			"pharmacy.overrides.stock_hold.block_held_movement",
		],
		"before_submit": [
			"pharmacy.overrides.storage.validate_bin_capacity",
			"pharmacy.overrides.controlled_drugs.require_custodian",
			"pharmacy.overrides.stock_adjustment.require_approval",
		],
		"on_submit": [
			"pharmacy.overrides.stock_inward.validate_inward_batches",
			"pharmacy.overrides.shelf_life.validate_shelf_life",
			"pharmacy.overrides.patient_order.update_patient_so_tracking",
		],
	},
	"Stock Reconciliation": {
		"validate": [
			"pharmacy.overrides.storage.validate_storage",
			"pharmacy.overrides.stock_adjustment.validate_adjustment",
		],
		"before_submit": [
			"pharmacy.overrides.storage.validate_bin_capacity",
			"pharmacy.overrides.controlled_drugs.require_custodian",
			"pharmacy.overrides.stock_adjustment.require_approval",
		],
		"on_submit": "pharmacy.overrides.stock_inward.validate_inward_batches",
	},
	"Material Request": {
		"validate": "pharmacy.overrides.material_request.validate_manual_indent",
		"before_submit": "pharmacy.overrides.material_request.before_submit_manual_indent",
	},
	"Sales Order": {
		"validate": [
			"pharmacy.overrides.patient_order.validate_patient_order",
			"pharmacy.overrides.quarantine.block_allocation",
			"pharmacy.overrides.stock_hold.block_held_allocation",
		],
		"on_update": "pharmacy.online.order_notifications.on_sales_order_status_change",
	},
	"Pick List": {
		"validate": [
			"pharmacy.overrides.quarantine.block_allocation",
			"pharmacy.overrides.stock_hold.block_held_allocation",
		],
	},
	"Stock Reservation Entry": {
		"validate": [
			"pharmacy.overrides.quarantine.block_allocation",
			"pharmacy.overrides.stock_hold.block_held_allocation",
		],
	},
	"Warehouse": {
		"on_update": "pharmacy.overrides.quarantine.sync_non_sellable",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"pharmacy.overrides.po_dispatch.send_ack_reminders",
		"pharmacy.overrides.pick_face.create_topups",
		"pharmacy.pharmacy.doctype.store_receipt.store_receipt.auto_receive_overdue",
	],
	"daily": [
		"pharmacy.pharmacy.doctype.drug_licence.drug_licence.update_statuses_and_send_alerts",
		"pharmacy.overrides.po_fulfilment.send_backorder_followups",
		"pharmacy.overrides.po_fulfilment.update_supplier_performance",
		"pharmacy.overrides.expiry_alerts.send_near_expiry_alerts",
		"pharmacy.overrides.tote_tracking.alert_overdue_totes",
	],
}

# Supplier portal: acknowledge Purchase Orders and confirm delivery dates
standard_portal_menu_items = [
	{
		"title": "Acknowledge Purchase Orders",
		"route": "/po-acknowledgement",
		"reference_doctype": "Purchase Order",
		"role": "Supplier",
	},
]

# Testing
# -------

before_tests = "pharmacy.tests.utils.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "pharmacy.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# closing a PO with goods still pending needs a short-close reason
override_whitelisted_methods = {
	"erpnext.buying.doctype.purchase_order.purchase_order.update_status": "pharmacy.overrides.po_fulfilment.update_status",
	"erpnext.buying.doctype.purchase_order.purchase_order.close_or_unclose_purchase_orders": "pharmacy.overrides.po_fulfilment.close_or_unclose_purchase_orders",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pharmacy.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pharmacy.utils.before_request"]
# after_request = ["pharmacy.utils.after_request"]

# Job Events
# ----------
# before_job = ["pharmacy.utils.before_job"]
# after_job = ["pharmacy.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"pharmacy.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

