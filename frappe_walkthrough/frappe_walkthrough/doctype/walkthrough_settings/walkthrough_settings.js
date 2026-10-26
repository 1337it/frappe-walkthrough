// Walkthrough Settings: Load, the AI tests and the design preview.

const API = "frappe_walkthrough.api.";

frappe.ui.form.on("Walkthrough Settings", {
	refresh(frm) {
		frm.trigger("show_status");
		frm.trigger("show_drafts");
		if (!frm._wt_realtime) {
			frm._wt_realtime = true;
			frappe.realtime.on("walkthrough_load", (st) => frm.events.paint_status(frm, st));
		}
	},

	async show_status(frm) {
		const st = await frappe.xcall(API + "load_status");
		frm.events.paint_status(frm, st);
		if (st.running) setTimeout(() => frm.trigger("show_status"), 3000);
	},

	paint_status(frm, st) {
		const esc = frappe.utils.escape_html;
		const counts = st.counts_now || {};
		const total = Object.values(counts).reduce((a, b) => a + b, 0);
		let html = '<div class="wt-status">';
		if (st.running) {
			const pct = st.total ? Math.round((100 * (st.done || 0)) / st.total) : 5;
			html += `<div><b>${esc(__("Loading…"))}</b> ${esc(__(st.phase || ""))}</div>` +
				`<div class="progress" style="height:6px;margin:8px 0"><div class="progress-bar" style="width:${pct}%"></div></div>`;
		} else if (st.phase === "Failed") {
			html += `<div class="text-danger">${esc(__("The last Load failed:"))} ${esc(st.error || "")}</div>`;
		}
		html += `<div><b>${total}</b> ${esc(__("walkthroughs switched on"))}` +
			(total ? " - " + Object.entries(counts).map(([k, v]) => `${esc(__(k))} ${v}`).join(", ") : "") + "</div>";
		if (st.edited) html += `<div class="text-muted">${st.edited} ${esc(__("edited by hand (kept by Load)"))}</div>`;
		if (st.finished && !st.running) html += `<div class="text-muted">${esc(__("Last loaded"))}: ${esc(frappe.datetime.prettyDate(st.finished))}</div>`;
		if (!total && !st.running) html += `<div class="text-muted">${esc(__("Press Load walkthroughs to build them."))}</div>`;
		html += "</div>";
		frm.get_field("status_html").$wrapper.html(html);
	},

	async load_walkthroughs(frm) {
		if (frm.is_dirty()) await frm.save();
		const st = await frappe.xcall(API + "load");
		frm.events.paint_status(frm, Object.assign({ counts_now: {} }, st));
		frappe.show_alert({ message: __("Loading walkthroughs in the background…"), indicator: "blue" });
		setTimeout(() => frm.trigger("show_status"), 2000);
	},

	/* Process walkthroughs waiting for review: play, open, switch on. */
	async show_drafts(frm) {
		const esc = frappe.utils.escape_html;
		const rows = await frappe.xcall(API + "drafts");
		const $w = frm.get_field("drafts_html").$wrapper;
		if (!rows.length) { $w.html(`<div class="text-muted small">${esc(__("No process walkthroughs yet - press Load walkthroughs."))}</div>`); return; }
		$w.html(`<div class="wt-drafts"><div class="small text-muted" style="margin-bottom:6px">${esc(__("Process walkthroughs"))} (${rows.length})</div>` +
			rows.map((r) => `<div class="wt-draft" data-key="${esc(r.name)}">
				<div class="wt-draft-t"><b>${esc(r.title)}</b> <span class="text-muted small">${esc(r.category || "")} · ${r.steps} ${esc(__("steps"))}${r.source === "AI" ? " · AI" : ""}</span>
				${r.check_result ? `<div class="small ${/^OK/.test(r.check_result) ? "text-success" : "text-danger"}">${esc(r.check_result)}</div>` : ""}</div>
				<div class="wt-draft-b">
					<button class="btn btn-xs btn-default" data-d="play">${esc(__("Play"))}</button>
					<a class="btn btn-xs btn-default" href="/app/walkthrough/${encodeURIComponent(r.name)}">${esc(__("Edit"))}</a>
					<button class="btn btn-xs ${r.enabled ? "btn-default" : "btn-primary"}" data-d="switch" data-on="${r.enabled ? 0 : 1}">${esc(r.enabled ? __("Switch off") : __("Switch on"))}</button>
				</div></div>`).join("") + "</div>");
		$w.find("[data-d]").on("click", async (e) => {
			const b = e.currentTarget, key = b.closest(".wt-draft").dataset.key;
			if (b.dataset.d === "play") frappe_walkthrough.wt.play_key(key);
			if (b.dataset.d === "switch") { await frappe.xcall(API + "switch", { key, on: b.dataset.on }); frm.trigger("show_drafts"); }
		});
	},

	/* Each draft's pages, forms, fields and buttons, looked for in this browser. */
	async check_drafts(frm) {
		const rows = await frappe.xcall(API + "drafts");
		if (!rows.length) return;
		const back = frappe.get_route();
		const d = frappe.show_progress(__("Checking"), 0, rows.length, __("Opening pages and forms…"));
		let bad = 0;
		for (const [i, r] of rows.entries()) {
			frappe.show_progress(__("Checking"), i, rows.length, r.title);
			let res;
			try { res = await frappe_walkthrough.wt.check(r.name, back); } catch (e) { res = { ok: false, notes: [String(e)] }; }
			if (!res.ok) bad++;
			await frappe.xcall(API + "save_check", { key: r.name, ok: res.ok ? 1 : 0, result: res.notes.join("; ") || __("every step found") });
		}
		frappe.hide_progress();
		await frappe.set_route("Form", "Walkthrough Settings");
		frappe.show_alert({ message: __("{0} checked, {1} with problems", [rows.length, bad]), indicator: bad ? "orange" : "green" });
		setTimeout(() => frm.reload_doc(), 800);
	},

	remove_generated(frm) {
		frappe.confirm(__("Delete the generated walkthroughs that were not edited by hand?"), async () => {
			const n = await frappe.xcall(API + "remove_generated");
			frappe.show_alert({ message: __("{0} removed", [n]), indicator: "green" });
			frm.trigger("show_status");
		});
	},

	async import_form_tours(frm) {
		const n = await frappe.xcall(API + "import_form_tours");
		frappe.show_alert({ message: __("{0} Form Tours imported", [n]), indicator: "green" });
		frm.trigger("show_status");
	},

	async test_jev(frm) {
		if (frm.is_dirty()) await frm.save();
		const r = await frappe.xcall(API + "test_jev");
		frappe.msgprint({ title: __("Ask box"), message: frappe.utils.escape_html(r.message), indicator: r.ok ? "green" : "red" });
	},

	async test_writer(frm) {
		if (frm.is_dirty()) await frm.save();
		const r = await frappe.xcall(API + "test_writer");
		frappe.msgprint({ title: __("Writer"), message: frappe.utils.escape_html(r.message), indicator: r.ok ? "green" : "red" });
	},

	/* The stage with the colours on this form, saved or not. */
	preview(frm) {
		const d = frm.doc;
		frappe_walkthrough.wt.preview({
			accent: d.accent_color, font: d.font_family, panel_width: d.panel_width, cursor: d.cursor_color,
			cursor_size: d.cursor_size, ring: d.ring_color || d.accent_color, dim: (d.dim_percent || 0) / 100,
			caption_bg: d.caption_bg, caption_text: d.caption_text, caption_width: d.caption_width, radius: d.radius,
		});
	},
});
