/* Frappe Walkthrough: the button, the panel and the player.

   Every desk page gets a Walkthrough button. Its panel lists the walkthroughs
   for the page you are on, then every walkthrough by category, with a filter
   box and - when an Ask key is set - a box for asking in plain words.

   Playing one moves a cursor across the real screen: it glides to each
   control, shows the press, then really clicks it. It never jumps to a page:
   it goes there through the sidebar, or by typing the name into the search
   bar, so the viewer learns the way. Create walkthroughs stop at each field
   and wait for the viewer to fill it in (Enter moves on), then for Save and
   Submit.

   Works on Frappe v15 (/app) and v16 (/desk). An app with its own sidebar
   can teach the player its way around - see WT.nav and
   frappe_walkthrough.nav.register() at the end.

   Everything the player does is in WT.act; a step names one of its actions.
*/
frappe.provide("frappe_walkthrough");

const WT = (frappe_walkthrough.wt = frappe_walkthrough.wt || {});
const CFG = () => (frappe.boot && frappe.boot.walkthrough) || {};

WT.sleep = (ms) => new Promise((r) => setTimeout(r, ms));
WT.reduced = (() => {
	const rm = CFG().reduced_motion;
	if (rm === "Always") return true;
	if (rm === "Never") return false;
	return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
})();
WT.speed = () => CFG().speed || 1;

// ------------------------------------------------------------ language

WT.RTL = ["ar", "he", "fa", "ur", "ps", "sd", "ug", "yi"];
WT._ui = {};

WT.lang = function () {
	try {
		const v = localStorage.getItem("wt-lang");
		if (v && (CFG().languages || []).some((l) => l.code === v)) return v;
	} catch (e) { /* private mode */ }
	return CFG().lang || "en";
};

WT.is_rtl = (lang) => WT.RTL.includes(String(lang || WT.lang()).split("-")[0]);

WT.set_lang = async function (lang) {
	try { localStorage.setItem("wt-lang", lang); } catch (e) { /* private mode */ }
	if (!WT._ui[lang]) WT._ui[lang] = await frappe.xcall("frappe_walkthrough.api.ui", { lang });
	WT.apply_lang();
	if (WT._panel && !WT._panel.hidden) WT.open_panel();
};

// an interface string in the current language; {0} placeholders as in __()
WT.t = function (text, args) {
	const lang = WT.lang();
	const dict = WT._ui[lang] || (lang === CFG().lang ? CFG().ui : null) || {};
	let out = dict[text] || text;
	(args || []).forEach((a, i) => { out = out.replace(`{${i}}`, a); });
	return out;
};

WT.apply_lang = function () {
	const lang = WT.lang();
	[WT._panel, WT._stage && WT._stage.cap].forEach((el) => {
		if (!el) return;
		el.setAttribute("dir", WT.is_rtl(lang) ? "rtl" : "ltr");
		el.setAttribute("lang", lang);
	});
	if (WT._stage) {
		const c = WT._stage.cap;
		c.querySelector('[data-a="next"]').textContent = WT.t("Next");
		c.querySelector('[data-a="stop"]').textContent = WT.t("Stop");
		c.querySelector('[data-a="pause"]').textContent = WT.t(WT.playing && WT.playing.paused ? "Play" : "Pause");
	}
};

// ------------------------------------------------------------ design

/* The settings' colours and sizes as CSS variables; the stylesheet reads only these. */
WT.apply_design = function () {
	const d = CFG().design || {};
	const root = document.documentElement.style;
	const set = (k, v) => v !== undefined && v !== null && v !== "" && root.setProperty(k, v);
	set("--wt-accent", d.accent);
	set("--wt-font", d.font || null);
	set("--wt-panel-width", (d.panel_width || 400) + "px");
	set("--wt-cursor", d.cursor);
	set("--wt-ring", d.ring);
	set("--wt-dim", `rgba(0, 0, 0, ${d.dim === undefined ? 0.14 : d.dim})`);
	set("--wt-cap-bg", d.caption_bg);
	set("--wt-cap-text", d.caption_text);
	set("--wt-cap-width", (d.caption_width || 340) + "px");
	set("--wt-radius", (d.radius === undefined ? 12 : d.radius) + "px");
	WT.cursor_size = d.cursor_size || 26;
	document.body.classList.toggle("wt-panel-left", CFG().panel_side === "left");
};

// ------------------------------------------------------------ where we are

WT.norm = (h) => {
	let v = String(h || "").split("?")[0].split("#")[0];
	try { v = decodeURIComponent(v); } catch (e) { /* leave it */ }
	return v.replace(/\/+$/, "").toLowerCase();
};

/* "/app" on v15, "/desk" on v16 - read from where we are, else the version. */
WT.base = function () {
	const seg = location.pathname.split("/")[1];
	if (seg === "app" || seg === "desk") return "/" + seg;
	const v = parseInt(((frappe.boot && frappe.boot.versions) || {}).frappe || "15", 10);
	return v >= 16 ? "/desk" : "/app";
};

/* A stored route ("sales-order", "query-report/General Ledger") as a path. */
WT.full = function (route) {
	let r = String(route || "").trim();
	r = r.replace(/^\/?(desk|app)\//, "").replace(/^\//, "");
	return WT.base() + "/" + r;
};
WT.rel = (route) => String(route || "").trim().replace(/^\/?(desk|app)\//, "").replace(/^\//, "");
WT.route_is = (route) => WT.norm(location.pathname) === WT.norm(WT.full(route));

/* The page, in the terms walkthroughs name their pages in. */
WT.context = function () {
	let route;
	try { route = frappe.get_route() || []; } catch (e) { return {}; }
	const [a, b, c] = route;
	if (a === "Workspaces") {
		const ws = b === "private" ? c : b;
		return { context: "Workspace:" + ws, workspace: ws, label: __(ws), type: "workspace" };
	}
	if ((a === "List" || a === "Tree" || a === "Report") && b) return { context: "DocType:" + b, doctype: b, label: __(b), type: "list" };
	if (a === "Form" && b) return { context: "DocType:" + b, doctype: b, label: __(b), name: c, type: "form" };
	if (a === "query-report" && b) return { context: "Report:" + b, label: __(b), type: "report" };
	if (route.length === 1 && a) {
		const pg = frappe.pages && frappe.pages[a] && frappe.pages[a].page;
		return { context: "Page:" + a, label: (pg && pg.title) || a, type: "page" };
	}
	return { label: "", type: "page" };
};

// ------------------------------------------------------------- the button

/* In the page head; on a page without one (v16's app grid at /desk) it
   floats at the bottom corner instead. */
WT.mount_button = function () {
	const cfg = CFG();
	const $head = $(".page-container:visible .page-head .page-actions, .page-head:visible .page-actions").first();
	const type = WT.context().type || "page";
	const wanted = cfg.show && !(cfg.on && cfg.on[type] === 0);
	const $where = $head.length ? $head : $("body");
	$(".wt-btn").not($where.children(".wt-btn")).remove();
	if (!wanted) { $(".wt-btn").remove(); return; }
	if ($where.children(".wt-btn").length) return;
	const $b = $('<button class="btn btn-default btn-sm wt-btn" type="button">' +
		'<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
		'<path d="M4 2.5v11l3.2-3 2.1 4.2 1.8-.9-2.1-4.2H13z" fill="currentColor"/></svg>' +
		"<span></span></button>");
	$b.find("span").text(cfg.label || WT.t("Walkthrough"));
	$b.on("click", () => WT.open_panel());
	if ($head.length) $b.prependTo($head);
	else $b.addClass("wt-float").appendTo("body");
};

// -------------------------------------------------------------- the panel

WT.panel = function () {
	if (WT._panel && document.body.contains(WT._panel)) return WT._panel;
	const el = document.createElement("div");
	el.className = "wt-panel";
	el.hidden = true;
	document.body.appendChild(el);
	el.addEventListener("click", (e) => {
		const t = e.target.closest("[data-act]");
		if (!t) return;
		const act = t.dataset.act;
		if (act === "close") WT.close_panel();
		else if (act === "cat") WT.toggle_cat(t.closest(".wt-cat"));
		else if (act === "play") WT.play_key(t.dataset.key);
		else if (act === "record") frappe_walkthrough.recorder.start();
	});
	el.addEventListener("change", (e) => {
		if (e.target.matches(".wt-lang")) WT.set_lang(e.target.value);
	});
	el.addEventListener("submit", (e) => {
		e.preventDefault();
		WT.ask(el.querySelector(".wt-ask input").value);
	});
	el.addEventListener("input", (e) => {
		if (e.target.matches(".wt-filter")) WT.render_list(e.target.value);
	});
	WT._panel = el;
	return el;
};

WT.open_panel = function () {
	const el = WT.panel();
	WT.ctx = WT.context();
	el.hidden = false;
	WT.data = null;
	WT.render_panel();
	frappe.xcall("frappe_walkthrough.api.catalogue", { context: WT.ctx.context, workspace: WT.ctx.workspace, lang: WT.lang() })
		.then((r) => {
			WT.data = r;
			WT.render_panel();
			if (r.ai) setTimeout(() => { const i = el.querySelector(".wt-ask input"); i && i.focus(); }, 60);
		});
};

WT.close_panel = function () {
	if (WT._panel) WT._panel.hidden = true;
};

WT.render_panel = function () {
	const el = WT.panel();
	const esc = frappe.utils.escape_html;
	const d = WT.data;
	const langs = CFG().languages || [];
	const cur = WT.lang();
	el.innerHTML =
		'<div class="wt-head"><div class="wt-head-t"><div class="wt-kicker">' + esc(WT.t("Walkthroughs")) + "</div>" +
		'<div class="wt-where">' + esc((WT.ctx && WT.ctx.label) || "") + "</div></div>" +
		(langs.length > 1 ? '<select class="wt-lang" aria-label="' + esc(WT.t("Language")) + '">' +
			langs.map((l) => `<option value="${esc(l.code)}"${l.code === cur ? " selected" : ""}>${esc(l.name)}</option>`).join("") +
			"</select>" : "") +
		'<button class="wt-x" type="button" data-act="close" aria-label="Close">&times;</button></div>' +
		(d && d.ai ? '<form class="wt-ask"><input type="text" placeholder="' + esc(WT.t("Ask how to do something…")) +
			'" autocomplete="off"><button type="submit">' + esc(WT.t("Ask")) + "</button>" +
			'<div class="wt-ask-note"></div></form>' : "") +
		'<input class="wt-filter" type="search" placeholder="' + esc(WT.t("Filter…")) + '">' +
		'<div class="wt-list">' + (d ? "" : '<div class="wt-empty">…</div>') + "</div>" +
		(CFG().can_record ? '<div class="wt-foot"><button type="button" class="btn btn-xs btn-default" data-act="record">' +
			'<span class="wt-rec-dot"></span> ' + esc(WT.t("Record a walkthrough")) + "</button></div>" : "");
	WT.apply_lang();
	if (d) WT.render_list("");
};

WT.item_html = function (it, n, highlight) {
	const esc = frappe.utils.escape_html;
	return '<button class="wt-item' + (it.key === highlight ? " is-match" : "") + '" data-act="play" data-key="' + esc(it.key) + '">' +
		'<span class="wt-n">' + n + "</span>" +
		'<span class="wt-body"><span class="wt-title">' + esc(it.title) + "</span>" +
		(it.summary ? '<span class="wt-sum">' + esc(it.summary) + "</span>" : "") + "</span>" +
		'<span class="wt-meta"><span class="wt-kind k-' + esc((it.kind || "").toLowerCase()) + '">' + esc(WT.t(it.kind || "")) + "</span>" +
		(it.kind === "Create" ? esc(WT.t("interactive")) : (it.steps_count || 0) + " " + esc(WT.t("steps"))) + "</span>" +
		'<span class="wt-play" aria-hidden="true">&#9654;</span></button>';
};

WT._hit = (q) => (it) => !q || [it.title, it.summary, it.title_en, it.summary_en, it.category_label]
	.some((s) => s && String(s).toLowerCase().includes(q));

/* Categories are drawn when opened: a big site has a thousand walkthroughs. */
WT.render_list = function (filter, highlight) {
	const d = WT.data;
	const list = WT.panel().querySelector(".wt-list");
	if (!d || !list) return;
	const esc = frappe.utils.escape_html;
	const q = (filter || "").trim().toLowerCase();
	const hit = WT._hit(q);
	WT._filter = q;
	WT._highlight = highlight;

	let html = "";
	const page = (d.on_page || []).filter(hit);
	if (!q || page.length) {
		html += '<div class="wt-sec">' + esc(WT.t("On this page")) + "</div>";
		html += page.length ? page.map((it, i) => WT.item_html(it, i + 1, highlight)).join("")
			: '<div class="wt-empty">' + esc(WT.t("Nothing to show here yet.")) + "</div>";
	}
	html += '<div class="wt-sec">' + esc(WT.t("All walkthroughs")) + "</div>";
	const home = d.home_category || (page[0] && page[0].category);
	(d.categories || []).forEach((cat, ci) => {
		const n = q ? cat.items.filter(hit).length : cat.items.length;
		if (!n) return;
		const open = q || cat.name === home || (highlight && cat.items.some((x) => x.key === highlight));
		html += '<div class="wt-cat' + (open ? " is-open" : "") + '" data-ci="' + ci + '">' +
			'<button type="button" class="wt-cat-h" data-act="cat"><span class="wt-chev">&#9656;</span>' +
			"<span>" + esc(cat.label || cat.name) + '</span><span class="wt-count">' + n + "</span></button>" +
			'<div class="wt-cat-b"></div></div>';
	});
	list.innerHTML = html;
	list.querySelectorAll(".wt-cat.is-open").forEach((c) => WT.fill_cat(c));
	const m = list.querySelector(".is-match");
	if (m) m.scrollIntoView({ block: "nearest" });
};

WT.fill_cat = function (el) {
	const cat = WT.data.categories[+el.dataset.ci];
	const items = cat.items.filter(WT._hit(WT._filter));
	el.querySelector(".wt-cat-b").innerHTML = items.map((it, i) => WT.item_html(it, i + 1, WT._highlight)).join("");
};

WT.toggle_cat = function (el) {
	el.classList.toggle("is-open");
	if (el.classList.contains("is-open") && !el.querySelector(".wt-item")) WT.fill_cat(el);
};

WT.ask = function (q) {
	const el = WT.panel();
	const note = el.querySelector(".wt-ask-note");
	if (!(q || "").trim() || !note) return;
	note.textContent = WT.t("Thinking…");
	el.querySelector(".wt-ask").classList.add("is-busy");
	const filter = el.querySelector(".wt-filter");
	if (filter) filter.value = "";
	frappe.xcall("frappe_walkthrough.api.ask", { question: q, context: WT.ctx.context, workspace: WT.ctx.workspace, lang: WT.lang() })
		.then((r) => {
			if (r.key && r.item) {
				note.textContent = r.item.title;
				WT.render_list("", r.key);
				setTimeout(() => WT.play_key(r.key), 700);
			} else if (r.guess && r.item) {
				note.textContent = WT.t("Not sure - is it this one?") + " " + r.item.title;
				WT.render_list("", r.guess);
			} else {
				note.textContent = WT.t(r.error ? "The assistant is unreachable right now." : "No walkthrough covers that yet.");
			}
		})
		.finally(() => { const f = el.querySelector(".wt-ask"); f && f.classList.remove("is-busy"); });
};

/* Fetch a walkthrough's steps and play it. */
WT.play_key = function (key) {
	return frappe.xcall("frappe_walkthrough.api.get", { key, lang: WT.lang() }).then((w) => {
		w.steps = (w.steps || []).map((st) => Object.assign({}, st, {
			do: st.action, doctype: st.ref_doctype, key: st.action === "key" ? st.text : undefined,
		}));
		return WT.play(w);
	});
};

// ------------------------------------------------------------- the stage

WT.stage = function () {
	if (WT._stage && document.body.contains(WT._stage.cursor)) return WT._stage;
	const size = WT.cursor_size || 26;
	const cursor = document.createElement("div");
	cursor.className = "wt-cursor";
	cursor.innerHTML =
		`<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">` +
		'<path d="M5 2.8v16.6l4.3-4 3 6.2 2.9-1.4-3-6.1H19z" fill="var(--wt-cursor, #1b1c1e)" stroke="#fff" ' +
		'stroke-width="1.4" stroke-linejoin="round"/></svg>';
	const ring = document.createElement("div");
	ring.className = "wt-ring";
	const cap = document.createElement("div");
	cap.className = "wt-cap";
	cap.innerHTML =
		'<div class="wt-cap-head"><span class="wt-cap-t"></span><span class="wt-cap-n"></span></div>' +
		'<div class="wt-cap-say"></div>' +
		'<div class="wt-cap-bar"><i></i></div>' +
		'<div class="wt-cap-btns">' +
		'<button type="button" data-a="pause"></button>' +
		'<button type="button" data-a="next"></button>' +
		'<button type="button" data-a="stop"></button></div>';
	[ring, cursor, cap].forEach((e) => { e.hidden = true; document.body.appendChild(e); });
	WT._stage = { cursor, ring, cap, x: window.innerWidth / 2, y: window.innerHeight / 2 };
	WT.apply_lang();
	cap.querySelector('[data-a="pause"]').addEventListener("click", () => WT.toggle_pause());
	cap.querySelector('[data-a="next"]').addEventListener("click", () => WT.skip());
	cap.querySelector('[data-a="stop"]').addEventListener("click", () => WT.stop());
	return WT._stage;
};

WT.move_to = async function (x, y) {
	const s = WT.stage();
	const d = Math.hypot(x - s.x, y - s.y);
	const ms = WT.reduced ? 120 : Math.min(1100, Math.max(380, d * 0.9)) * WT.speed();
	s.cursor.style.transitionDuration = ms + "ms";
	s.cursor.style.transform = `translate(${x}px, ${y}px)`;
	s.x = x; s.y = y;
	await WT.sleep(ms + 60);
};

WT.press = async function (x, y) {
	const s = WT.stage();
	s.cursor.classList.add("is-down");
	const rip = document.createElement("div");
	rip.className = "wt-ripple";
	rip.style.left = x + "px";
	rip.style.top = y + "px";
	document.body.appendChild(rip);
	await WT.sleep(180);
	s.cursor.classList.remove("is-down");
	setTimeout(() => rip.remove(), 700);
	await WT.sleep(120);
};

WT.ring = function (el) {
	const s = WT.stage();
	if (!el) { s.ring.hidden = true; return; }
	const r = el.getBoundingClientRect();
	const pad = 6;
	Object.assign(s.ring.style, {
		left: r.left - pad + "px", top: r.top - pad + "px",
		width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px",
	});
	s.ring.hidden = false;
};

WT.caption = function (text, el, side) {
	const s = WT.stage();
	// another driver of the cursor (an assistant) can speak in its own window
	if (WT.quiet) { s.cap.hidden = true; return; }
	const p = WT.playing;
	s.cap.hidden = false;
	s.cap.querySelector(".wt-cap-t").textContent = p ? p.item.title : "";
	s.cap.querySelector(".wt-cap-n").textContent = p ? `${p.i + 1} / ${p.item.steps.length}` : "";
	s.cap.querySelector(".wt-cap-say").textContent = text || "";
	// beside the target, on whichever side has room; centred low if no target
	const w = s.cap.offsetWidth || 340, h = s.cap.offsetHeight || 120, m = 14;
	let left, top;
	if (el) {
		const r = el.getBoundingClientRect();
		top = r.bottom + m + h < window.innerHeight ? r.bottom + m : Math.max(m, r.top - h - m);
		left = Math.min(window.innerWidth - w - m, Math.max(m, r.left + Math.min(r.width, 260) / 2 - 40));
		// a whole panel - or a date field, whose calendar opens underneath - takes it beside
		if (side || r.height > window.innerHeight * 0.6) {
			top = Math.max(m, Math.min(window.innerHeight - h - m, r.top + 40));
			left = r.right + m + w < window.innerWidth ? r.right + m : Math.max(m, r.left - w - m);
		}
	} else {
		left = (window.innerWidth - w) / 2;
		top = window.innerHeight - h - 40;
	}
	s.cap.style.left = left + "px";
	s.cap.style.top = top + "px";
};

// ------------------------------------------------------------- targets

/* On screen. Not offsetParent: that is null for anything position:fixed - the
   search bar, sidebars - which made them look absent. */
WT.visible = (el) => {
	if (!el || !el.getClientRects().length) return false;
	const r = el.getBoundingClientRect();
	return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden";
};

WT.PAGE = ".page-container:not([style*='display: none'])";

WT.find = function (spec) {
	if (!spec) return null;
	const [kind, ...rest] = String(spec).split(":");
	const arg = rest.join(":");
	const all = (sel) => { try { return [...document.querySelectorAll(sel)].filter(WT.visible); } catch (e) { return []; } };
	const page = WT.PAGE;
	switch (kind) {
		case "sidebar":
		case "rail": {
			if (!arg) return WT.nav.sidebar();
			const rows = WT.nav.rails().flatMap((r) => [...r.querySelectorAll(`[data-id="${CSS.escape(arg)}"] > .standard-sidebar-item, [item-name="${CSS.escape(arg)}"]`)])
				.filter(WT.visible);
			return rows[0] || WT.nav.rails().flatMap((r) => [...r.querySelectorAll("a, .standard-sidebar-item")])
				.filter(WT.visible).find((e) => e.textContent.trim() === arg) || null;
		}
		case "search":
			return all("#navbar-modal-search, .navbar .search-bar, #navbar-search")[0] || null;
		case "field":
			return all(`${page} .frappe-control[data-fieldname="${CSS.escape(arg)}"]`)[0] || null;
		case "tab":
			return all(`${page} .form-tabs .nav-link`).find((e) => e.textContent.trim() === arg || e.textContent.trim() === __(arg)) || null;
		case "btn":
			return all(`${page} .page-head button, ${page} .page-head a.btn`)
				.find((e) => e.textContent.trim().toLowerCase().includes(__(arg).toLowerCase())) || null;
		case "menu": {        // menu:<group>/<item> - the group's button (its item is found by WT.act.make)
			const group = arg.split("/")[0];
			return all(`${page} .page-head .inner-group-button[data-label="${encodeURIComponent(__(group))}"] > button, ` +
				`${page} .page-head .inner-group-button[data-label="${encodeURIComponent(group)}"] > button`)[0] || null;
		}
		case "primary":
			return all(`${page} .page-head .primary-action`)[0] || null;
		case "title":
			return all(`${page} .page-head .title-area, ${page} .page-head .page-title`)[0] || null;
		case "row":
			return all(`${page} .list-row-container .list-row`)[0] || all(".dt-row, .db-row")[0] || null;
		case "filters":
			return all(`${page} .standard-filter-section, ${page} .page-form, ${page} .filter-section`)[0] || null;
		case "report-filters":
			return all(`${page} .page-form`)[0] || null;
		case "report-table":
			return all(`${page} .dt-header, ${page} .dt-scrollable, ${page} .report-wrapper`)[0] || null;
		case "menu":
			return all(`${page} .page-actions .menu-btn-group, ${page} .page-actions .btn-default`)[0] || null;
		case "css":
			return all(arg)[0] || null;
	}
	return null;
};

/* A field on a tab that is not open: open the tab first, visibly. */
WT.to_field_tab = async function (fieldname, show) {
	const frm = window.cur_frm;
	const f = frm && frm.fields_dict && frm.fields_dict[fieldname];
	if (!f || !f.tab || !f.tab.is_active || f.tab.is_active()) return false;
	const link = f.tab.tab_link && f.tab.tab_link.find(".nav-link")[0];
	if (show && link && WT.visible(link)) await WT.act.click({ say: WT.t("The {0} tab.", [__(f.tab.df.label || "")]) }, link);
	else f.tab.set_active();
	await WT.sleep(250);
	return true;
};

WT.wait_for = async function (spec, ms) {
	const end = Date.now() + (ms || 6000);
	while (Date.now() < end) {
		if (WT.stopped() && !WT.quiet) return null;
		const el = typeof spec === "function" ? spec() : WT.find(spec);
		if (el) return el;
		await WT.sleep(120);
	}
	return null;
};

WT.center = function (el) {
	const r = el.getBoundingClientRect();
	// aim a little in from the left on wide things, the way a hand would
	return { x: r.left + Math.min(r.width / 2, 48), y: r.top + r.height / 2 };
};

WT.bring_into_view = async function (el) {
	const r = el.getBoundingClientRect();
	if (r.top < 120 || r.bottom > window.innerHeight - 40) {
		el.scrollIntoView({ block: "center", behavior: WT.reduced ? "auto" : "smooth" });
		await WT.sleep(WT.reduced ? 50 : 450);
	}
};

WT.settle = async function () {
	await WT.sleep(250);
	await WT.wait_for(() => (frappe.dom && frappe.dom.freeze_count ? null : document.body), 4000);
	await WT.sleep(500);
};

// ------------------------------------------------------- getting around
/* WT.nav knows the desk's layout. The stock driver uses Frappe's own sidebar
   and search bar (v15 and v16). An app with its own layout registers a
   driver with frappe_walkthrough.nav.register({...}) overriding any of these. */

WT.STOCK_NAV = {
	// the sidebar(s) that hold links, most specific first
	rails() {
		return [...document.querySelectorAll(".body-sidebar, .desk-sidebar, .layout-side-section .list-sidebar")]
			.filter(WT.visible);
	},
	sidebar() {
		return WT.nav.rails()[0] || null;
	},
	// a link to this path, if a sidebar has one (shown or folded)
	link_for(route) {
		const want = WT.norm(WT.full(route));
		for (const r of WT.nav.rails()) {
			const a = [...r.querySelectorAll("a[href]")].find((x) => WT.norm(x.getAttribute("href")) === want);
			if (a) return a;
		}
		return null;
	},
	// bring a link on screen: unfold its group
	async reveal(a) {
		if (WT.visible(a)) return true;
		const own = a.closest(".sidebar-item-container");
		const sec = own && own.parentElement && own.parentElement.closest(".sidebar-item-container");
		const head = sec && sec.querySelector(":scope > .standard-sidebar-item");
		if (head && WT.visible(head)) {
			await WT.act.click({ say: WT.t("Open the {0} group.", [sec.getAttribute("data-id") || head.textContent.trim()]) }, head);
			await WT.sleep(250);
		}
		return WT.visible(a);
	},
	// the visible way there; true when it got there by clicking
	async reach(route, step) {
		const a = WT.nav.link_for(route);
		if (a && (await WT.nav.reveal(a))) {
			await WT.act.click(step, a.closest(".standard-sidebar-item") || a);
			return true;
		}
		return false;
	},
	// open the search bar; returns its input
	async open_search(say) {
		const modal_btn = document.querySelector("#navbar-modal-search");
		if (modal_btn) {                       // v16: a search dialog
			const btn = WT.visible(modal_btn) ? modal_btn : null;
			if (btn) await WT.act.click({ say }, btn);
			else { WT.caption(say); $(modal_btn).click(); }
			return WT.wait_for(() => document.querySelector(".modal.show #navbar-search"), 3000);
		}
		const inp = document.querySelector("#navbar-search");   // v15: in the navbar
		if (inp && WT.visible(inp)) {
			await WT.act.click({ say }, inp);
			inp.focus();
			return inp;
		}
		return null;
	},
	results(inp) {
		const scope = inp.closest(".modal") || inp.closest(".awesomplete") || document;
		return [...scope.querySelectorAll(".awesomplete ul li, ul[role=listbox] li")].filter(WT.visible);
	},
};

WT.nav = Object.assign({}, WT.STOCK_NAV);

frappe.provide("frappe_walkthrough.nav");
frappe_walkthrough.nav.register = function (driver) {
	Object.assign(WT.nav, driver || {});
};

WT.label_for = function (route) {
	const r = WT.norm(WT.full(route)).replace(/^\/(desk|app)\//, "");
	if (r.startsWith("query-report/")) {
		const n = String(route).split("/").pop();
		try { return __(decodeURIComponent(n)); } catch (e) { return n; }
	}
	const words = r.split("/")[0].split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
	return __(words);
};

WT.via_search = async function (route) {
	const label = WT.label_for(route);
	const inp = await WT.nav.open_search(WT.t("{0} is not in the sidebar - search for it by name.", [label]));
	if (!inp) { frappe.set_route(WT.rel(route)); await WT.settle(); return; }
	WT.caption(WT.t("Type its name and pick it from the results."), inp);
	const r = inp.getBoundingClientRect();
	await WT.move_to(r.left + 40, r.top + r.height / 2);
	inp.focus();
	for (let i = 1; i <= label.length && !WT.stopped(); i++) {
		inp.value = label.slice(0, i);
		inp.dispatchEvent(new Event("input", { bubbles: true }));
		await WT.sleep(WT.reduced ? 10 : 70 * WT.speed());
	}
	const lis = (await WT.wait_for(() => { const l = WT.nav.results(inp); return l.length ? l : null; }, 3000)) || [];
	const low = label.toLowerCase();
	const is_report = WT.norm(route).includes("query-report/");
	const li = lis.find((e) => {
		const t = e.innerText.trim().toLowerCase();
		return t.startsWith(low) && (is_report ? t.includes(__("Report").toLowerCase()) : /list$/.test(t.split("\n")[0]));
	}) || lis.find((e) => e.innerText.trim().toLowerCase().startsWith(low));
	if (li) {
		const c = WT.center(li);
		await WT.move_to(c.x, c.y);
		WT.ring(li);
		await WT.press(c.x, c.y);
		li.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
		li.click();
		WT.ring(null);
	}
	await WT.settle();
	if (!WT.route_is(route)) {
		$(".modal.show").modal("hide");
		frappe.set_route(WT.rel(route));
		await WT.settle();
	}
};

// ------------------------------------------------------------- actions

WT.act = {
	async point(step) {
		const el = await WT.wait_for(step.target, 5000);
		if (!el) { WT.ring(null); WT.caption(step.say); return; }
		await WT.bring_into_view(el);
		const c = WT.center(el);
		WT.caption(step.say, el);
		await WT.move_to(c.x, c.y);
		WT.ring(el);
	},

	async click(step, el) {
		el = el || (await WT.wait_for(step.target, 6000));
		if (!el) { WT.caption(step.say); return; }
		await WT.bring_into_view(el);
		const c = WT.center(el);
		WT.caption(step.say, el);
		await WT.move_to(c.x, c.y);
		WT.ring(el);
		await WT.press(c.x, c.y);
		const target = el.querySelector("a.item-anchor") || el;
		target.click();
		await WT.settle();
		WT.ring(null);
	},

	/* Never a jump: the sidebar, else the search bar. */
	async go(step) {
		const route = step.route;
		if (WT.route_is(route)) { WT.caption(step.say); return; }
		const reached = await WT.nav.reach(route, step);
		if (!reached) await WT.via_search(route);
		await WT.wait_for(() => (WT.route_is(route) ? document.body : null), 6000);
		if (!WT.route_is(route)) { frappe.set_route(WT.rel(route)); await WT.settle(); }
		await WT.sleep(400);
	},

	async open(step) {
		// on a record of this kind already: that is the one the viewer means
		const f = window.cur_frm;
		if (f && f.doctype === step.doctype && !f.is_new() && WT.visible(f.page.wrapper[0])) {
			WT.caption(step.say);
			await WT.sleep(400);
			return;
		}
		const list = frappe.router.slug(step.doctype);
		if (!WT.route_is(list)) await WT.act.go({ route: list, say: step.say });
		const link = await WT.wait_for(() => [...document.querySelectorAll(
			`${WT.PAGE} .list-row-container .list-subject a[href], ${WT.PAGE} .list-row-container a[data-name]`
		)].find(WT.visible) || null, 6000);
		if (!link) { WT.caption(step.say); return; }
		const name = link.dataset.name || decodeURIComponent((link.getAttribute("href") || "").split("/").pop());
		await WT.act.click({ say: step.say }, link);
		await WT.wait_for(() => (window.cur_frm && cur_frm.doctype === step.doctype && !cur_frm.is_new()
			&& (!name || cur_frm.doc.name === name) && WT.visible(cur_frm.page.wrapper[0]) ? document.body : null), 8000);
		await WT.sleep(500);
	},

	/* The list's Add, then the full form - never the quick-entry dialog. */
	async new(step) {
		const list = frappe.router.slug(step.doctype);
		if (!WT.route_is(list)) await WT.act.go({ route: list, say: step.say });
		const add = await WT.wait_for("primary", 3000);
		if (add) {
			await WT.bring_into_view(add);
			const c = WT.center(add);
			WT.caption(step.say, add);
			await WT.move_to(c.x, c.y);
			WT.ring(add);
			await WT.press(c.x, c.y);
			WT.ring(null);
		} else {
			WT.caption(step.say);
		}
		await new Promise((res) => frappe.model.with_doctype(step.doctype, res));
		const doc = frappe.model.get_new_doc(step.doctype);
		WT.created.push(doc);
		frappe.set_route("Form", step.doctype, doc.name);
		await WT.wait_for(() => (window.cur_frm && cur_frm.doc && cur_frm.doc.name === doc.name ? document.body : null), 8000);
		await WT.sleep(700);
	},

	/* Text drawn over a field; the document never sees it. */
	async type(step) {
		const el = await WT.wait_for(step.target, 5000);
		if (!el) { WT.caption(step.say); return; }
		await WT.act.point({ target: step.target, say: step.say });
		const box = el.querySelector(".control-input input, .control-input textarea, .control-input select, .control-value") || el;
		const r = box.getBoundingClientRect();
		await WT.press(r.left + 24, r.top + r.height / 2);
		const ghost = document.createElement("div");
		ghost.className = "wt-ghost";
		Object.assign(ghost.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" });
		document.body.appendChild(ghost);
		WT.ghosts.push(ghost);
		const text = step.text || "";
		for (let i = 1; i <= text.length; i++) {
			if (WT.stopped()) break;
			ghost.textContent = text.slice(0, i);
			await WT.sleep(WT.reduced ? 5 : 45 * WT.speed());
		}
	},

	/* The next document, made from this one: open the Create menu, pick it,
	   and the new form opens with everything carried over. The menu appears
	   once the document is saved (or submitted), so it is waited for. */
	async make(step) {
		const [group, ...rest] = String(step.target || "").replace(/^menu:/, "").split("/");
		const item = rest.join("/");
		const btn = await WT.wait_for("menu:" + group + "/" + item, 8000);
		if (!btn) {
			// the menu comes once the document is saved and submitted: without that, this part cannot be shown
			WT.caption(WT.t("Save and submit it first - then Create → {0} appears.", [__(item)]));
			await WT.sleep(2500);
			return false;
		}
		const from = window.cur_frm && cur_frm.doc && cur_frm.doc.name;
		await WT.act.click({ say: step.say }, btn);
		const wrap = btn.closest(".inner-group-button");
		const li = await WT.wait_for(() => [...wrap.querySelectorAll(".dropdown-item")].find((a) =>
			WT.visible(a) && [encodeURIComponent(__(item)), encodeURIComponent(item)].includes(a.getAttribute("data-label"))) || null, 3000);
		if (!li) { WT.caption(step.say); return false; }
		const c = WT.center(li);
		await WT.move_to(c.x, c.y);
		WT.ring(li);
		await WT.press(c.x, c.y);
		li.click();
		WT.ring(null);
		// some open a small dialog first (which items, which date): the viewer answers it
		await WT.wait_for(() => {
			if (window.cur_frm && cur_frm.doc && cur_frm.doc.name !== from && (!step.doctype || cur_frm.doctype === step.doctype)) return document.body;
			return null;
		}, 15000);
		await WT.sleep(700);
	},

	async tab(step) {
		const el = await WT.wait_for("tab:" + step.label, 4000);
		if (!el) { WT.caption(step.say); return; }
		await WT.act.click(step, el);
	},

	async key(step) {
		if ((step.key || step.text) === "Escape") {
			$(".modal:visible").modal("hide");
			if (frappe.search && frappe.search.dialog && frappe.search.dialog.hide) frappe.search.dialog.hide();
		}
		await WT.sleep(300);
	},

	/* A field the viewer fills in for real: the cursor clicks into it and the
	   player waits. Enter (Tab) moves on; a choice moves on when chosen; a
	   table waits for Next, since rows are added by clicking. */
	async input(step) {
		await WT.to_field_tab(String(step.target || "").replace(/^field:/, ""), true);
		const ctl = await WT.wait_for(step.target, 5000);
		if (!ctl) { WT.caption(step.say); await WT.sleep(1200); return; }   // hidden by the form's own rules
		await WT.bring_into_view(ctl);
		const name = String(step.target).replace(/^field:/, "");
		const f = window.cur_frm && cur_frm.fields_dict[name];
		const df = (f && f.df) || {};
		WT.covered.add(name);
		const box = ctl.querySelector(
			".control-input input:not([type=hidden]):not([type=checkbox]), .control-input textarea, " +
			".control-input select, input[type=checkbox]");
		const kind = ["Table", "Table MultiSelect"].includes(df.fieldtype) ? "table"
			: !box ? "table"
			: ["Date", "Datetime", "Time"].includes(df.fieldtype) ? "date"
			: box.tagName === "SELECT" ? "select"
			: box.type === "checkbox" ? "check"
			: box.tagName === "TEXTAREA" ? "text" : "line";
		const aim = box || ctl;
		const r = aim.getBoundingClientRect();
		const x = r.left + Math.min(r.width / 2, 40), y = r.top + r.height / 2;
		WT.caption(step.say, ctl);
		await WT.move_to(x, y);
		WT.ring(ctl);
		await WT.press(x, y);
		if (box && kind !== "table") box.focus();
		const hint = WT.t({
			line: "Type it, then press Enter",
			text: "Type it, then press Ctrl + Enter",
			select: "Choose an option",
			check: "Tick it or press Next",
			date: "Type it or pick it from the calendar, then press Enter",
			table: "Add the rows, then press Next",
		}[kind]);
		WT.waiting(true, hint, ctl, kind === "date");
		await WT.wait_user(box, kind, window.cur_frm, ctl, name);
		WT.waiting(false);
		if (box && box.blur && kind !== "table") {
			await WT.sleep(250);       // let a link's dropdown commit its pick
			box.blur();
		}
		await WT.sleep(250);
		WT.ring(null);
	},

	/* Everything else the form will not save without, in form order,
	   re-read after each field: answering one can make another mandatory. */
	async fill(step) {
		const frm = window.cur_frm;
		if (!frm) return;
		const asked = new Set();
		for (let n = 0; n < 30 && !WT.stopped(); n++) {
			const next = (frm.fields || []).find((fld) => {
				const df = fld.df || {};
				if (!df.fieldname || asked.has(df.fieldname) || WT.covered.has(df.fieldname)) return false;
				if (!df.reqd || df.read_only || df.hidden || df.fieldname === "naming_series") return false;
				if (["Section Break", "Column Break", "Tab Break", "HTML", "Button"].includes(df.fieldtype)) return false;
				if (!WT.visible(fld.wrapper && (fld.wrapper[0] || fld.wrapper)) && !(fld.tab && fld.tab.is_active && !fld.tab.is_active()
					&& fld.disp_status !== "None")) return false;
				const v = frm.doc[df.fieldname];
				return v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length);
			});
			if (!next) break;
			asked.add(next.df.fieldname);
			await WT.act.input({
				target: "field:" + next.df.fieldname,
				say: (n === 0 && step.say ? step.say + " " : "") + WT.t("{0} is required.", [__(next.df.label || next.df.fieldname)]),
			});
		}
	},

	/* The viewer saves it themselves; if the form refuses, they fix it and save again. */
	async save(step) {
		const frm = window.cur_frm;
		const btn = await WT.wait_for("primary", 3000);
		if (btn) {
			await WT.bring_into_view(btn);
			const c = WT.center(btn);
			WT.caption(step.say, btn);
			await WT.move_to(c.x, c.y);
			WT.ring(btn);
		} else {
			WT.caption(step.say);
		}
		WT.waiting(true, WT.t("Press Save, or Ctrl + S"), btn);
		await WT.wait_user(null, "save", frm);
		WT.waiting(false);
		WT.ring(null);
		if (frm && !frm.is_new()) {
			WT.caption(frm.meta.is_submittable
				? WT.t("Saved as {0}. Submit it when it is ready to go.", [frm.doc.name])
				: WT.t("Saved as {0}.", [frm.doc.name]));
		}
	},

	/* The viewer submits it themselves; the player waits until it really is. */
	async submit(step) {
		const frm = window.cur_frm;
		if (!frm || frm.is_new()) {
			WT.caption(WT.t("Save it first - there is nothing to submit yet."));
			await WT.sleep(1800);
			return;
		}
		if (frm.doc.docstatus === 1) return;
		const label = __("Submit").toLowerCase();
		const btn = (await WT.wait_for(() => {
			const b = WT.find("primary");
			return b && b.textContent.trim().toLowerCase().includes(label) ? b : null;
		}, 4000)) || WT.find("primary");
		if (btn) {
			await WT.bring_into_view(btn);
			const c = WT.center(btn);
			WT.caption(step.say, btn);
			await WT.move_to(c.x, c.y);
			WT.ring(btn);
		} else {
			WT.caption(step.say);
		}
		WT.waiting(true, WT.t("Press Submit, then confirm"), btn);
		await WT.wait_user(null, "submit", frm);
		WT.waiting(false);
		WT.ring(null);
		if (frm.doc.docstatus === 1) WT.caption(WT.t("Submitted: {0}.", [frm.doc.name]));
	},

	async say(step) {
		WT.ring(null);
		WT.caption(step.say);
	},
};

// ------------------------------------------------------------- your turn

WT.waiting = function (on, hint, el, side) {
	const p = WT.playing;
	if (p) p.waiting = !!on;
	const cap = WT.stage().cap;
	cap.classList.toggle("is-waiting", !!on);
	let tip = cap.querySelector(".wt-cap-tip");
	if (!tip) {
		tip = document.createElement("div");
		tip.className = "wt-cap-tip";
		cap.insertBefore(tip, cap.querySelector(".wt-cap-bar"));
	}
	tip.textContent = on ? hint || "" : "";
	if (on && el) WT.caption(cap.querySelector(".wt-cap-say").textContent, el, side);
};

/* Resolves when the viewer has done their part, presses Next, or stops. */
WT.wait_user = function (box, kind, frm, ctl, fieldname) {
	const p = WT.playing;
	// a link field's autocomplete swallows Enter before listeners on its input
	// hear it - so keys are heard on the document, in the capture phase
	const within = (t) => !!(t && ((ctl && ctl.contains(t)) || (box && box === t)));
	return new Promise((resolve) => {
		let done = false;
		let picked = 0;
		const finish = () => {
			if (done) return;
			done = true;
			clearInterval(poll);
			document.removeEventListener("keydown", onkey, true);
			document.removeEventListener("change", onchange, true);
			resolve();
		};
		const onkey = (e) => {
			if (!within(e.target)) return;
			if (e.key === "Tab") return setTimeout(finish, 60);
			if (e.key !== "Enter") return;
			if (kind === "text" && !(e.ctrlKey || e.metaKey)) return;
			if (kind === "text") e.preventDefault();
			setTimeout(finish, 300);     // a link field's Enter picks from its dropdown first
		};
		const onchange = (e) => {
			if (within(e.target) && (kind === "select" || kind === "check")) setTimeout(finish, 200);
		};
		if (box || ctl) {
			document.addEventListener("keydown", onkey, true);
			document.addEventListener("change", onchange, true);
		}
		const poll = setInterval(() => {
			if (!p || p.stopped || p.skip) return finish();
			if (kind === "save" && frm && !frm.is_new()) return finish();
			if (kind === "submit" && frm && frm.doc.docstatus === 1) return finish();
			// a date picked from the calendar: move on once it is set and the calendar has closed
			if (kind === "date" && frm && fieldname && frm.doc[fieldname] && !document.querySelector(".datepicker.active")) {
				if (!picked) picked = Date.now();
				else if (Date.now() - picked > 450) return finish();
			}
		}, 150);
	});
};

// ------------------------------------------------------------- playback

WT.created = [];
WT.ghosts = [];
WT.covered = new Set();
WT.INTERACTIVE = new Set(["input", "fill", "save", "submit", "make"]);
WT.stopped = () => !WT.playing || WT.playing.stopped;
WT.dwell = (text) => (WT.reduced ? 1200 : Math.min(7000, 1800 + (text || "").length * 42) * WT.speed());

WT.wait_dwell = async function (ms) {
	const p = WT.playing;
	const bar = WT.stage().cap.querySelector(".wt-cap-bar i");
	let left = ms;
	while (left > 0 && p && !p.stopped && !p.skip) {
		if (!p.paused) left -= 100;
		bar.style.width = Math.max(0, 100 - (left / ms) * 100) + "%";
		await WT.sleep(100);
	}
	bar.style.width = "0%";
};

WT.play = async function (item) {
	if (!item) return;
	WT.close_panel();
	if (WT.playing) WT.stop();
	const s = WT.stage();
	const p = (WT.playing = { item, i: 0, paused: false, stopped: false, skip: false, waiting: false });
	WT.covered = new Set();
	document.body.classList.add("wt-on");
	s.cursor.hidden = false;
	s.cursor.style.transitionDuration = "0ms";
	const btn = document.querySelector(".wt-btn");
	if (btn) {
		const r = btn.getBoundingClientRect();
		s.x = r.left + 20; s.y = r.top + r.height / 2;
	}
	s.cursor.style.transform = `translate(${s.x}px, ${s.y}px)`;
	WT.apply_lang();
	for (p.i = 0; p.i < item.steps.length; p.i++) {
		if (p.stopped) break;
		const step = item.steps[p.i];
		p.skip = false;
		while (p.paused && !p.stopped) await WT.sleep(150);
		try {
			const done = await (WT.act[step.do] || WT.act.say)(step);
			if (done === false && step.do === "make") {
				// nothing was made: skip that document's steps, up to the next one made or opened
				while (p.i + 1 < item.steps.length && !["make", "go", "new", "open", "say"].includes(item.steps[p.i + 1].do)) p.i++;
			}
		} catch (e) {
			console.warn("walkthrough step failed", step, e);     // a demo should not die
		}
		if (p.stopped) break;
		WT.clear_ghosts();
		if (WT.INTERACTIVE.has(step.do)) continue;           // the viewer just did their part
		WT.caption(step.say, step.target && WT.find(step.target));
		await WT.wait_dwell(WT.dwell(step.say));
		WT.clear_ghosts();
	}
	if (!p.stopped) WT.finish(item);
};

WT.finish = function (item) {
	const s = WT.stage();
	WT.ring(null);
	s.cap.querySelector(".wt-cap-n").textContent = "";
	s.cap.querySelector(".wt-cap-say").textContent = WT.t("That is it. Open Walkthrough again for another.");
	setTimeout(() => { if (WT.playing && WT.playing.item === item) WT.stop(); }, 2600);
};

WT.toggle_pause = function () {
	const p = WT.playing;
	if (!p) return;
	p.paused = !p.paused;
	WT.stage().cap.querySelector('[data-a="pause"]').textContent = WT.t(p.paused ? "Play" : "Pause");
	WT.stage().cap.classList.toggle("is-paused", p.paused);
};

WT.skip = function () {
	if (WT.playing) { WT.playing.skip = true; WT.playing.paused = false; }
};

WT.clear_ghosts = function () {
	WT.ghosts.forEach((g) => g.remove());
	WT.ghosts = [];
};

WT.stop = function () {
	const p = WT.playing;
	if (p) p.stopped = true;
	WT.playing = null;
	WT.clear_ghosts();
	const s = WT._stage;
	if (s) { s.cursor.hidden = true; s.ring.hidden = true; s.cap.hidden = true; s.cap.classList.remove("is-paused"); }
	document.body.classList.remove("wt-on");
	// blank forms the walkthrough opened are thrown away - unless the viewer
	// typed into one, in which case it is their work now
	WT.created.forEach((d) => {
		try {
			const open = window.cur_frm && cur_frm.doc && cur_frm.doc.name === d.name;
			if (open && (cur_frm.is_dirty() || !cur_frm.is_new())) return;
			if (!locals[d.doctype] || !locals[d.doctype][d.name] || !locals[d.doctype][d.name].__islocal) return;
			if (open) frappe.set_route("List", d.doctype);
			frappe.model.remove_from_locals(d.doctype, d.name);
		} catch (e) { /* already gone */ }
	});
	WT.created = [];
};

// ------------------------------------------------------------- wiring

$(document).on("app_ready", function () {
	if (WT._wired) return;
	WT._wired = true;
	WT.apply_design();

	const remount = () => setTimeout(WT.mount_button, 350);
	frappe.router.on("change", remount);
	$(document).on("page-change", remount);
	remount();
	setTimeout(WT.mount_button, 1500);     // a workspace draws its head late

	document.addEventListener("keydown", (e) => {
		if (e.key !== "Escape") return;
		// while it waits for the viewer, Esc belongs to whatever they are typing in
		if (WT.playing && WT.playing.waiting) return;
		if (WT.playing) WT.stop();
		else WT.close_panel();
	});
	// the viewer taking the mouse pauses the demo rather than fighting it
	document.addEventListener("pointerdown", (e) => {
		if (!WT.playing || !e.isTrusted || WT.playing.paused || WT.playing.waiting) return;
		if (e.target.closest(".wt-cap")) return;
		WT.toggle_pause();
	}, true);
	window.addEventListener("resize", () => WT.playing && WT.ring(null));
});

/* Check a walkthrough without playing it for real: open each page and each
   new form it uses and look for every field, tab and button it points at.
   Nothing is saved - the blank forms are thrown away. Returns {ok, notes}. */
WT.check = async function (key, back) {
	const w = await frappe.xcall("frappe_walkthrough.api.get", { key });
	const notes = [];
	let dt = null;
	const opened = [];
	const open_new = async (doctype) => {
		await new Promise((res) => frappe.model.with_doctype(doctype, res));
		const doc = frappe.model.get_new_doc(doctype);
		opened.push(doc);
		frappe.set_route("Form", doctype, doc.name);
		const ok = await WT.wait_for(() => (window.cur_frm && cur_frm.doc && cur_frm.doc.name === doc.name ? document.body : null), 8000);
		if (!ok) notes.push(__("{0}: the form did not open", [doctype]));
		await WT.sleep(500);
	};
	WT.playing = { item: w, stopped: false, check: true };       // lets wait_for run
	try {
		for (const [i, st] of w.steps.entries()) {
			const n = `#${i + 1} ${st.action}`;
			if (st.action === "go") {
				frappe.set_route(WT.rel(st.route));
				const ok = await WT.wait_for(() => (WT.route_is(st.route) ? document.body : null), 8000);
				if (!ok) notes.push(`${n}: ${st.route} ${__("did not open")}`);
				await WT.sleep(400);
			} else if (st.action === "new" || st.action === "make" || st.action === "open") {
				dt = st.ref_doctype;
				if (!dt) { notes.push(`${n}: ${__("no DocType")}`); continue; }
				await new Promise((res) => frappe.model.with_doctype(dt, res));
				if (!frappe.model.can_create(dt)) { notes.push(`${n}: ${__("no permission to create {0}", [dt])}`); continue; }
				await open_new(dt);
			} else if (st.action === "input") {
				const f = String(st.target || "").replace(/^field:/, "");
				const frm = window.cur_frm;
				if (!frm || !frm.fields_dict[f]) notes.push(`${n}: ${__("no field {0} on {1}", [f, dt || "?"])}`);
				else {
					await WT.to_field_tab(f, false);
					if (!WT.find(st.target)) notes.push(`${n}: ${__("{0} is hidden until other fields are filled", [f])}`);
				}
			} else if (st.action === "tab") {
				if (!WT.find("tab:" + st.label)) notes.push(`${n}: ${__("no tab {0}", [st.label])}`);
			} else if (["click", "point", "type"].includes(st.action) && st.target && !/^(primary|row|title|filters|menu|report-|sidebar|search)/.test(st.target)) {
				if (!(await WT.wait_for(st.target, 2500))) notes.push(`${n}: ${__("{0} not found", [st.target])}`);
			}
		}
	} finally {
		WT.playing = null;
		if (back) { await frappe.set_route(back); await WT.sleep(400); }
		opened.forEach((d) => { try { frappe.model.remove_from_locals(d.doctype, d.name); } catch (e) { /* gone */ } });
	}
	const hard = notes.filter((x) => !/hidden until/.test(x));
	return { ok: !hard.length, notes };
};

/* For the settings page's Preview button: the stage with the current design. */
WT.preview = async function (design) {
	if (design) { frappe.boot.walkthrough = Object.assign({}, CFG(), { design: Object.assign({}, CFG().design, design) }); }
	WT.apply_design();
	if (WT._stage) { WT._stage.cursor.remove(); WT._stage.ring.remove(); WT._stage.cap.remove(); WT._stage = null; }
	const target = document.querySelector(".page-head .primary-action") || document.querySelector(".page-head");
	return WT.play({
		key: "preview", title: CFG().label || "Walkthrough", steps: [
			{ do: "point", target: "sidebar", say: WT.t("Walkthrough is on every page. It lists what can be done on that page first, then everything else.") },
			{ do: "point", target: target ? "css:.page-head .primary-action, .page-head" : null, say: WT.t("Saved as {0}.", ["PREVIEW-0001"]) },
		],
	});
};
