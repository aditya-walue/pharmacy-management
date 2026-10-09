// Purchase Suggestion — client-side buttons

frappe.ui.form.on("Purchase Suggestion", {
  refresh(frm) {
    // ── Generate Suggestions button (Draft only) ──────────────────────────
    if (frm.doc.docstatus === 0) {
      frm.add_custom_button(__("Generate Suggestions"), () => {
        if (!frm.doc.warehouse) {
          frappe.msgprint(__("Please select a Warehouse before generating suggestions."));
          return;
        }
        frappe.show_progress(__("Generating…"), 10, 100);
        frm
          .call({
            method: "generate",
            doc: frm.doc,
            freeze: true,
            freeze_message: __("Calculating purchase requirements…"),
          })
          .then((r) => {
            frappe.hide_progress();
            if (r && r.message) {
              frm.reload_doc();
            }
          });
      }, __("Actions"));
    }

    // ── Create Purchase Orders button (Submitted, not yet PO Created) ─────
    if (frm.doc.docstatus === 1 && frm.doc.status !== "PO Created") {
      frm.add_custom_button(__("Create Purchase Orders"), () => {
        const items_with_qty = (frm.doc.items || []).filter(
          (r) => (r.ordered_qty || 0) > 0
        );
        if (!items_with_qty.length) {
          frappe.msgprint(__("No items with Ordered Qty > 0 found."));
          return;
        }

        frappe.confirm(
          __("Create Purchase Orders for {0} items?", [items_with_qty.length]),
          () => {
            frm
              .call({
                method: "make_purchase_orders",
                doc: frm.doc,
                freeze: true,
                freeze_message: __("Creating Purchase Orders…"),
              })
              .then((r) => {
                if (r && r.message && r.message.length) {
                  frm.reload_doc();
                  // Open first PO for quick review
                  frappe.set_route("Form", "Purchase Order", r.message[0]);
                }
              });
          }
        );
      }, __("Actions"));
    }

    // ── Indicator badge ───────────────────────────────────────────────────
    const color = { Draft: "grey", Submitted: "blue", "PO Created": "green" }[
      frm.doc.status
    ] || "grey";
    frm.page.set_indicator(frm.doc.status || "Draft", color);
  },

  // Auto-set today when warehouse changes
  warehouse(frm) {
    if (!frm.doc.as_of_date) {
      frm.set_value("as_of_date", frappe.datetime.get_today());
    }
  },
});
