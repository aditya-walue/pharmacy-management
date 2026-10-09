// ERPNext POS — Pharmacy Search: barcode / brand / salt, stock, batches (FEFO) with expiry and MRP, loose units

frappe.provide("pharmacy.pos");

// the POS controller is built asynchronously after the page loads; retry briefly until it exists
pharmacy.pos.when_ready = function (tries = 20) {
	if (window.cur_pos && cur_pos.page) return pharmacy.pos.attach();
	if (tries) setTimeout(() => pharmacy.pos.when_ready(tries - 1), 500);
};
$(document).on("page-change", () => pharmacy.pos.when_ready());
pharmacy.pos.when_ready();

pharmacy.pos.attach = function () {
	if (frappe.get_route_str() !== "point-of-sale" || !window.cur_pos || cur_pos.__pharmacy) return;
	cur_pos.__pharmacy = true;
	cur_pos.page.add_button(__("Pharmacy Search"), () => pharmacy.pos.search_dialog(), { btn_class: "btn-primary" });
	frappe.ui.keys.add_shortcut({
		shortcut: "ctrl+k", action: () => pharmacy.pos.search_dialog(), page: cur_pos.page,
		description: __("Pharmacy Search"),
	});
};

pharmacy.pos.search_dialog = function () {
	const warehouse = cur_pos.settings.warehouse;
	const d = new frappe.ui.Dialog({
		title: __("Pharmacy Search — {0}", [warehouse]),
		size: "extra-large",
		fields: [
			{ fieldname: "text", fieldtype: "Data", label: __("Scan barcode, or type brand / generic (salt)") },
			{ fieldname: "results", fieldtype: "HTML" },
		],
	});
	const render = (items) => {
		if (!items.length) {
			d.fields_dict.results.$wrapper.html(`<p class="text-muted">${__("No match")}</p>`);
			return;
		}
		const esc = frappe.utils.escape_html;
		d.fields_dict.results.$wrapper.html(items.map((it, i) => {
			const units = (it.loose ? it.uoms : it.uoms.filter((u) => u.uom === (it.batches[0]?.mrp_uom || it.sales_uom)))
				.map((u) => `<option value="${esc(u.uom)}" ${u.uom === (it.batches[0]?.mrp_uom || it.sales_uom) ? "selected" : ""}>${esc(u.uom)}</option>`).join("");
			const batches = it.batches.map((b, j) => `<tr>
				<td><input type="radio" name="batch-${i}" value="${esc(b.batch_no)}" ${j === 0 ? "checked" : ""}></td>
				<td>${esc(b.batch_no)}${j === 0 ? ` <span class="indicator-pill green">${__("FEFO")}</span>` : ""}</td>
				<td>${frappe.datetime.str_to_user(b.expiry_date) || ""} <span class="text-muted">(${b.days_to_expiry ?? ""} ${__("days")})</span></td>
				<td>${format_currency(b.mrp)} / ${esc(b.mrp_uom || "")}</td><td>${b.qty} ${esc(it.stock_uom)}</td></tr>`).join("");
			return `<div class="frappe-card p-3 mb-3" data-idx="${i}">
				<div class="d-flex justify-content-between"><div><b>${esc(it.item_name)}</b> <span class="text-muted">${esc(it.item_code)}</span>
					${it.rx ? `<span class="indicator-pill red">Rx ${esc(it.category || "")}</span>` : ""}
					<div class="small text-muted">${esc(it.salt || "")} ${esc(it.strength || "")}${it.loose ? " · " + __("loose sale allowed") : ""}</div></div>
					<div><b>${it.stock}</b> ${esc(it.stock_uom)} ${__("in stock")}</div></div>
				${it.batches.length ? `<table class="table table-sm mt-2"><tr><th></th><th>${__("Batch")}</th><th>${__("Expiry")}</th><th>${__("MRP")}</th><th>${__("Stock")}</th></tr>${batches}</table>
				<div class="d-flex" style="gap:8px"><select class="form-control input-sm uom" style="width:140px">${units}</select>
					<input type="number" class="form-control input-sm qty" value="1" min="1" style="width:100px">
					<button class="btn btn-sm btn-primary add">${__("Add to Bill")}</button></div>`
				: `<p class="text-danger small mt-2">${__("No sellable batch here (out of stock, expired or on hold).")}</p>`}
				${it.substitutes.length ? `<div class="small mt-2">${__("Substitutes")}: ${it.substitutes.map((s) => `<a class="sub" data-code="${esc(s)}">${esc(s)}</a>`).join(", ")}</div>` : ""}
			</div>`;
		}).join(""));
		d.fields_dict.results.$wrapper.find(".add").on("click", function () {
			const card = $(this).closest("[data-idx]");
			const it = items[card.data("idx")];
			const batch_no = card.find(`input[name=batch-${card.data("idx")}]:checked`).val();
			const batch = it.batches.find((b) => b.batch_no === batch_no);
			const uom = card.find(".uom").val();
			const factor = (it.uoms.find((u) => u.uom === uom) || { conversion_factor: 1 }).conversion_factor;
			const pack = (it.uoms.find((u) => u.uom === batch.mrp_uom) || { conversion_factor: 1 }).conversion_factor;
			const rate = (batch.mrp / pack) * factor; // the server re-prices from the batch MRP on save
			cur_pos.on_cart_update({
				field: "qty", value: flt(card.find(".qty").val()) || 1,
				item: { item_code: it.item_code, batch_no, uom, stock_uom: it.stock_uom, rate },
			});
			frappe.show_alert({ message: __("Added {0}", [it.item_name]), indicator: "green" });
			d.set_value("text", "");
			d.fields_dict.text.set_focus();
		});
		d.fields_dict.results.$wrapper.find(".sub").on("click", function () {
			d.set_value("text", $(this).data("code"));
			search();
		});
	};
	const search = () => {
		const text = (d.get_value("text") || "").trim();
		if (text.length < 2) return;
		frappe.xcall("pharmacy.overrides.pos_billing.pharmacy_search", { text, warehouse, posting_date: cur_pos.frm.doc.posting_date })
			.then(render);
	};
	d.fields_dict.text.$input.on("change", search);
	d.show();
	d.fields_dict.text.set_focus();
};
