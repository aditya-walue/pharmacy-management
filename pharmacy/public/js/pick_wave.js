// Pick Wave — indents, FEFO allocation, handheld zone picking into totes, short picks, sealing, dispatch

const PW = "pharmacy.pharmacy.doctype.pick_wave.pick_wave";

frappe.ui.form.on("Pick Wave", {
	refresh(frm) {
		const status = frm.doc.status;
		if (["Draft", "Allocated"].includes(status)) {
			frm.add_custom_button(__("Get Indents"), () =>
				frm.call({ method: "get_indents", doc: frm.doc, freeze: true }).then(() => frm.reload_doc()), __("Plan"));
			if (frm.doc.indents && frm.doc.indents.length) {
				frm.add_custom_button(__("Allocate (FEFO)"), () =>
					frm.call({ method: "allocate", doc: frm.doc, freeze: true }).then(() => frm.reload_doc()), __("Plan"));
			}
		}
		if (["Allocated", "Picking"].includes(status) && !frm.is_dirty()) {
			frm.add_custom_button(__("Pick"), () => pick_dialog(frm)).addClass("btn-primary");
		}
		if (["Picking", "Picked"].includes(status)) {
			frm.add_custom_button(__("Seal Tote"), () => seal_dialog(frm), __("Pack"));
			frm.add_custom_button(__("Resolve Short Lines"), () => short_dialog(frm), __("Pack"));
		}
		if (status === "Picked" && !frm.is_dirty()) {
			frm.add_custom_button(__("Dispatch"), () =>
				frappe.confirm(__("Create dispatch documents for every store on this wave?"), () =>
					frappe.xcall(`${PW}.dispatch`, { wave: frm.doc.name }).then((docs) => {
						frappe.msgprint(__("Dispatched: {0}", [docs.join(", ")]));
						frm.reload_doc();
					})));
		}
	},
});

function pick_dialog(frm) {
	const zones = [...new Set((frm.doc.items || []).filter((r) => r.status === "Pending").map((r) => r.zone || ""))];
	const dialog = new frappe.ui.Dialog({
		title: __("Pick"),
		fields: [
			{ fieldname: "zone", fieldtype: "Select", label: __("Your Zone"), options: ["", ...zones].join("\n") },
			{ fieldname: "todo", fieldtype: "HTML" },
			{ fieldname: "bin", fieldtype: "Data", label: __("1. Scan Bin"), reqd: 1 },
			{ fieldname: "code", fieldtype: "Data", label: __("2. Scan Batch / Item"), reqd: 1 },
			{ fieldname: "qty", fieldtype: "Float", label: __("3. Qty"), reqd: 1 },
			{ fieldname: "tote", fieldtype: "Data", label: __("4. Scan Tote"), reqd: 1 },
		],
		primary_action_label: __("Confirm Pick"),
		primary_action(v) {
			frappe
				.xcall(`${PW}.pick_scan`, { wave: frm.doc.name, bin_code: v.bin, code: v.code, qty: v.qty, tote: v.tote })
				.then((r) => {
					frappe.show_alert({ message: __("{0}: {1} of {2} picked", [r.item_code, r.picked, r.of]), indicator: "green" });
					frm.reload_doc().then(() => show_todo(frm, dialog));
					["code", "qty"].forEach((f) => dialog.set_value(f, null));
					dialog.fields_dict.bin.set_focus();
				});
		},
	});
	const show_todo = () => {
		const zone = dialog.get_value("zone");
		const rows = (frm.doc.items || []).filter((r) => r.status === "Pending" && (!zone || (r.zone || "") === zone));
		dialog.fields_dict.todo.$wrapper.html(rows.length
			? `<table class="table table-sm small"><tr><th>${__("Bin")}</th><th>${__("Item")}</th><th>${__("Batch")}</th><th>${__("Qty")}</th></tr>${rows
				.map((r) => `<tr><td>${frappe.utils.escape_html(r.source_bin)}</td><td>${frappe.utils.escape_html(r.item_code)}${r.is_cold_chain ? " ❄" : ""}${r.is_scheduled ? " 🔒" : ""}</td><td>${frappe.utils.escape_html(r.batch_no || "")}</td><td>${r.qty - (r.picked_qty || 0)}</td></tr>`)
				.join("")}</table>`
			: `<p class="text-muted">${__("Nothing left to pick here.")}</p>`);
	};
	dialog.fields_dict.zone.$input.on("change", show_todo);
	dialog.fields_dict.bin.$input.on("change", () => dialog.fields_dict.code.set_focus());
	dialog.fields_dict.code.$input.on("change", () => dialog.fields_dict.qty.set_focus());
	show_todo();
	dialog.show();
	dialog.fields_dict.bin.set_focus();
}

function seal_dialog(frm) {
	frappe.prompt(
		[
			{ fieldname: "tote", fieldtype: "Link", options: "Tote", label: __("Tote"), reqd: 1,
				get_query: () => ({ filters: { current_wave: frm.doc.name, status: "In Use" } }) },
			{ fieldname: "seal_no", fieldtype: "Data", label: __("Seal No"), reqd: 1 },
			{ fieldname: "ice_packs", fieldtype: "Int", label: __("Ice Packs (cold box)") },
			{ fieldname: "temperature", fieldtype: "Data", label: __("Temperature at Packing °C (cold box)") },
		],
		(v) => frappe.xcall(`${PW}.seal_tote`, v).then(() => frm.reload_doc()),
		__("Seal Tote"),
		__("Seal")
	);
}

function short_dialog(frm) {
	const pending = (frm.doc.items || []).filter((r) => r.status === "Pending");
	const open = (frm.doc.items || []).filter((r) => r.status === "Short" && !r.short_action);
	const options = [
		...pending.map((r) => `MARK|${r.name}|${__("Mark short")}: ${r.item_code} ${r.source_bin} (${r.qty - (r.picked_qty || 0)})`),
		...open.map((r) => `RESOLVE|${r.name}|${__("Resolve")}: ${r.item_code} ${__("short")} ${r.short_qty}`),
	];
	if (!options.length) {
		frappe.msgprint(__("No short lines to handle."));
		return;
	}
	frappe.prompt(
		[
			{ fieldname: "line", fieldtype: "Select", label: __("Line"), reqd: 1, options: options.join("\n") },
			{ fieldname: "action", fieldtype: "Select", label: __("Action (for short lines)"), options: "\nBackorder\nSubstitute\nCancel" },
		],
		(v) => {
			const [kind, row] = v.line.split("|");
			const call = kind === "MARK"
				? frappe.xcall(`${PW}.mark_short`, { wave: frm.doc.name, row_name: row })
				: frappe.xcall(`${PW}.resolve_short`, { wave: frm.doc.name, row_name: row, action: v.action });
			call.then(() => frm.reload_doc());
		},
		__("Short Picks"),
		__("Apply")
	);
}
