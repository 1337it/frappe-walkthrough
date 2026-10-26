/* Record a walkthrough: do the task once, and it becomes a walkthrough.

   Started from the panel (System Manager or Walkthrough Manager). While it
   records, a bar at the top counts the steps. It notes what a person does,
   in the player's own terms:
     the pages they go to          -> go
     a new or an opened record     -> new / open
     each field they fill          -> input (once per field)
     Save, Submit                  -> save / submit
     Create → <document>           -> make
     a form tab, a page button     -> tab / click
   On Stop it shows the steps with a caption each - written from the field
   labels, or by the Writer when one is set up - to edit, name and save.

   It survives a page reload (sessionStorage) and ignores its own bar, the
   walkthrough panel and the player.
*/
frappe.provide("frappe_walkthrough");

const REC = (frappe_walkthrough.recorder = frappe_walkthrough.recorder || {});
const RW = () => frappe_walkthrough.wt;
const KEY = "wt-recording";

REC.state = null;

REC.load = function () {
	try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (e) { return null; }
};
REC.persist = function () {
	try { sessionStorage.setItem(KEY, JSON.stringify(REC.state)); } catch (e) { /* full */ }
	REC.paint();
};

REC.start = function () {
	RW().close_panel();
	const ctx = RW().context();
	REC.state = { steps: [], contexts: ctx.context ? [ctx.context] : [], filled: {}, started: ctx };
	REC.persist();
	REC.listen();
	REC.route();            // where it starts is the first step
};

REC.cancel = function () {
	REC.unlisten();
	REC.state = null;
	try { sessionStorage.removeItem(KEY); } catch (e) { /* blocked */ }
	REC.paint();
};

// ------------------------------------------------------------ the bar

REC.paint = function () {
	let bar = document.querySelector(".wt-rec-bar");
	if (!REC.state) { if (bar) bar.remove(); document.body.classList.remove("wt-recording"); return; }
	if (!bar) {
		bar = document.createElement("div");
		bar.className = "wt-rec-bar";
		bar.innerHTML = '<span class="wt-rec-dot"></span><b></b><span class="wt-rec-n"></span>' +
			'<button type="button" data-r="stop" class="btn btn-xs btn-primary"></button>' +
			'<button type="button" data-r="cancel" class="btn btn-xs btn-default"></button>';
		bar.addEventListener("click", (e) => {
			const r = e.target.closest("[data-r]");
			if (r && r.dataset.r === "stop") REC.finish();
			if (r && r.dataset.r === "cancel") frappe.confirm(RW().t("Throw this recording away?"), REC.cancel);
		});
		document.body.appendChild(bar);
	}
	document.body.classList.add("wt-recording");
	bar.querySelector("b").textContent = RW().t("Recording");
	bar.querySelector(".wt-rec-n").textContent = `${REC.state.steps.length} ${RW().t("steps")}`;
	bar.querySelector('[data-r="stop"]').textContent = RW().t("Stop and save");
	bar.querySelector('[data-r="cancel"]').textContent = RW().t("Cancel");
};

// ------------------------------------------------------------ listening

REC.add = function (step) {
	const steps = REC.state.steps;
	const last = steps[steps.length - 1];
	// a run of page changes is one move: keep where it ended
	if (step.action === "go" && last && last.action === "go") steps.pop();
	if (last && JSON.stringify(last) === JSON.stringify(step)) return;
	steps.push(step);
	const c = RW().context().context;
	if (c && !REC.state.contexts.includes(c)) REC.state.contexts.push(c);
	REC.persist();
};

REC.route = function () {
	if (!REC.state) return;
	let r;
	try { r = frappe.get_route() || []; } catch (e) { return; }
	const steps = REC.state.steps;
	const last = steps[steps.length - 1];
	if (r[0] === "Form" && r[1]) {
		const dt = r[1], name = String(r[2] || "");
		if (name.startsWith("new-")) {
			// made from the previous document by Create → …: that step already says so
			if (last && last.action === "make" && !last.ref_doctype) { last.ref_doctype = dt; REC.persist(); return; }
			if (steps.some((x) => x.action === "new" && x.ref_doctype === dt) && REC._new_dt === dt) return;
			REC.add({ action: "new", ref_doctype: dt, _label: __(dt) });
			return;
		}
		// the same document, saved: its name changed, nobody opened anything
		if (last && ["save", "submit", "input", "fill"].includes(last.action) && REC._form_dt === dt) return;
		REC.add({ action: "open", ref_doctype: dt, _label: __(dt) });
		return;
	}
	const rel = RW().rel(location.pathname);
	if (!rel) return;
	REC.add({ action: "go", route: decodeURIComponent(rel), _label: (RW().context().label || rel) });
};

/* The quick-entry dialog a list's Add can open: its fields are the form's. */
REC.quick_entry = function (el) {
	const d = window.cur_dialog;
	if (!d || !d.$wrapper || !d.$wrapper[0].contains(el)) return null;
	const dt = d.doctype || (d.meta && d.meta.name) || REC._new_dt;
	return dt ? { doctype: dt, dialog: d } : null;
};

REC.on_change = function (e) {
	if (!REC.state || REC.ignore(e.target)) return;
	const ctl = e.target.closest && e.target.closest(".frappe-control[data-fieldname]");
	if (!ctl) return;
	const qe = REC.quick_entry(ctl);
	if (qe) {
		const fname = ctl.getAttribute("data-fieldname");
		const df = (qe.dialog.fields_dict[fname] || {}).df || frappe.meta.get_docfield(qe.doctype, fname) || {};
		const k = qe.doctype + "." + fname;
		if (!fname || REC.state.filled[k] || !frappe.meta.get_docfield(qe.doctype, fname)) return;
		REC.state.filled[k] = 1;
		REC._form_dt = qe.doctype;
		REC.add({ action: "input", target: "field:" + fname, _label: __(df.label || fname), _type: df.fieldtype });
		return;
	}
	const frm = window.cur_frm;
	if (!frm || !frm.page || !frm.page.wrapper[0].contains(ctl)) return;
	const fname = ctl.getAttribute("data-fieldname");
	const f = frm.fields_dict[fname];
	if (!f || !f.df) return;
	if (ctl.closest(".grid-row, .form-grid")) return;      // a table's own cells: the table is one step
	const k = frm.doctype + "." + fname;
	if (REC.state.filled[k]) return;
	REC.state.filled[k] = 1;
	REC._form_dt = frm.doctype;
	REC.add({ action: "input", target: "field:" + fname, _label: __(f.df.label || fname), _type: f.df.fieldtype });
};

REC.on_click = function (e) {
	if (!REC.state || !e.isTrusted || REC.ignore(e.target)) return;
	const t = e.target;
	const frm = window.cur_frm;
	const item = t.closest(".inner-group-button .dropdown-item");
	if (item) {
		const group = decodeURIComponent(item.closest(".inner-group-button").getAttribute("data-label") || "");
		const label = decodeURIComponent(item.getAttribute("data-label") || "");
		REC.add({ action: "make", target: `menu:${group}/${label}`, _label: label });
		return;
	}
	const tab = t.closest(".form-tabs .nav-link");
	if (tab) { REC.add({ action: "tab", label: tab.textContent.trim(), _label: tab.textContent.trim() }); return; }
	// a list's Add: a new one of that list (a quick-entry dialog or the full form)
	const primary_list = t.closest(".page-head .primary-action");
	if (primary_list && window.cur_list && RW().context().type === "list") {
		REC._new_dt = cur_list.doctype;
		REC.add({ action: "new", ref_doctype: cur_list.doctype, _label: __(cur_list.doctype) });
		return;
	}
	// the quick-entry dialog's Save
	const qe_save = t.closest(".modal.show .btn-primary");
	if (qe_save && REC.quick_entry(qe_save)) { REC.add({ action: "save" }); return; }
	const primary = t.closest(".page-head .primary-action");
	if (primary && frm) {
		const text = primary.textContent.trim().toLowerCase();
		REC._form_dt = frm.doctype;
		if (text.includes(__("Submit").toLowerCase())) REC.add({ action: "submit" });
		else if (text.includes(__("Save").toLowerCase())) REC.add({ action: "save" });
		return;
	}
	const btn = t.closest(".page-head button, .page-head a.btn");
	if (btn && !btn.closest(".inner-group-button") && !btn.classList.contains("dropdown-toggle")) {
		const text = btn.textContent.trim();
		if (text) REC.add({ action: "click", target: "btn:" + text, _label: text });
	}
};

REC.on_key = function (e) {
	if (!REC.state || !(e.ctrlKey || e.metaKey) || (e.key || "").toLowerCase() !== "s") return;
	if (window.cur_frm) { REC._form_dt = cur_frm.doctype; REC.add({ action: "save" }); }
};

REC.ignore = (el) => !!(el && el.closest && el.closest(".wt-rec-bar, .wt-panel, .wt-cap, .wt-btn, .modal-dialog .wt-rec-dialog"));

REC.listen = function () {
	if (REC._on) return;
	REC._on = true;
	if (!REC._route) {                    // once; it does nothing when not recording
		REC._route = () => setTimeout(REC.route, 400);
		frappe.router.on("change", REC._route);
	}
	document.addEventListener("change", REC.on_change, true);
	document.addEventListener("click", REC.on_click, true);
	document.addEventListener("keydown", REC.on_key, true);
};

REC.unlisten = function () {
	if (!REC._on) return;
	REC._on = false;
	document.removeEventListener("change", REC.on_change, true);
	document.removeEventListener("click", REC.on_click, true);
	document.removeEventListener("keydown", REC.on_key, true);
};

// ------------------------------------------------------------ saving

/* A caption from what is known about the step, in the viewer's words. */
REC.caption = function (st) {
	const L = st._label || "";
	switch (st.action) {
		case "go": return RW().t("Open {0}.", [L]);
		case "new": return RW().t("Add a new {0}.", [L]);
		case "open": return RW().t("Open a {0}.", [L]);
		case "input":
			return ["Link", "Select", "Dynamic Link"].includes(st._type) ? RW().t("Choose the {0}.", [L])
				: ["Date", "Datetime", "Time"].includes(st._type) ? RW().t("Set the {0}.", [L])
				: ["Table", "Table MultiSelect"].includes(st._type) ? RW().t("Add the {0}.", [L])
				: RW().t("Enter the {0}.", [L]);
		case "save": return RW().t("Save it.");
		case "submit": return RW().t("Submit it.");
		case "make": return RW().t("Create → {0}.", [L]);
		case "tab": return RW().t("The {0} tab.", [L]);
		case "click": return RW().t("Press {0}.", [L]);
	}
	return "";
};

REC.finish = function () {
	const st = REC.state;
	if (!st || !st.steps.length) { REC.cancel(); return; }
	REC.unlisten();
	const rows = st.steps.map((s, i) => ({ idx: i + 1, action: s.action, what: s.target || s.route || s.ref_doctype || s.label || "", say: REC.caption(s) }));
	const first = st.steps.find((s) => s.ref_doctype);
	const d = new frappe.ui.Dialog({
		title: RW().t("Record a walkthrough"),
		size: "large",
		fields: [
			{ fieldname: "title", fieldtype: "Data", label: RW().t("Title"), reqd: 1 },
			{ fieldname: "cb", fieldtype: "Column Break" },
			{ fieldname: "kind", fieldtype: "Select", label: RW().t("Kind"), options: "Process\nCreate\nRead\nReport\nBoard\nTour", default: "Process" },
			{ fieldname: "category", fieldtype: "Data", label: RW().t("Category"), default: (st.started && st.started.workspace) || "" },
			{ fieldname: "sb", fieldtype: "Section Break" },
			{ fieldname: "summary", fieldtype: "Small Text", label: RW().t("Summary"),
				description: RW().t("One plain sentence. The Ask box matches questions against it.") },
			{ fieldname: "steps", fieldtype: "Table", label: RW().t("Steps"), cannot_add_rows: true, in_place_edit: true, data: rows,
				fields: [
					{ fieldname: "action", fieldtype: "Data", label: RW().t("Action"), in_list_view: 1, read_only: 1, columns: 1 },
					{ fieldname: "what", fieldtype: "Data", label: RW().t("Target"), in_list_view: 1, read_only: 1, columns: 3 },
					{ fieldname: "say", fieldtype: "Small Text", label: RW().t("Caption"), in_list_view: 1, columns: 6 },
				] },
		],
		primary_action_label: RW().t("Save walkthrough"),
		primary_action: async (v) => {
			const kept = (v.steps || []).map((r) => r.idx);
			const out = st.steps.map((s, i) => {
				const r = (v.steps || []).find((x) => x.idx === i + 1);
				const clean = Object.fromEntries(Object.entries(s).filter(([k]) => !k.startsWith("_")));
				return r ? Object.assign(clean, { say: r.say || "" }) : null;
			}).filter((s, i) => s && kept.includes(i + 1));
			const key = await frappe.xcall("frappe_walkthrough.api.save_recorded", {
				title: v.title, steps: JSON.stringify(out), category: v.category, kind: v.kind, summary: v.summary,
				contexts: JSON.stringify(st.contexts),
			});
			d.hide();
			REC.cancel();
			frappe.show_alert({ message: RW().t("Saved. It is in the Walkthrough panel now."), indicator: "green" });
			return key;
		},
		secondary_action_label: CFG_writer() ? RW().t("Write the captions") : null,
		secondary_action: CFG_writer() ? async () => {
			const v = d.get_values(true);
			const r = await frappe.xcall("frappe_walkthrough.api.draft_captions", {
				title: v.title || "", steps: JSON.stringify(st.steps.map((s) => Object.fromEntries(Object.entries(s).filter(([k]) => !k.startsWith("_"))))),
			});
			if (r && r.captions) {
				const grid = d.fields_dict.steps;
				grid.df.data.forEach((row, i) => { if (r.captions[i]) row.say = r.captions[i]; });
				grid.grid.refresh();
				if (r.summary && !v.summary) d.set_value("summary", r.summary);
			} else if (r && r.error) {
				frappe.msgprint(r.error);
			}
		} : null,
	});
	d.$wrapper.find(".modal-dialog").addClass("wt-rec-dialog");
	d.onhide = () => { if (REC.state) REC.listen(); };   // closed without saving: still recording
	d.show();
};

function CFG_writer() {
	return !!(frappe.boot.walkthrough && frappe.boot.walkthrough.writer);
}

// a reload in the middle of a recording carries on
$(document).on("app_ready", () => {
	const st = REC.load();
	if (st) { REC.state = st; REC.listen(); REC.paint(); }
});
