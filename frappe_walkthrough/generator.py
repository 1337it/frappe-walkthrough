"""Walkthroughs made from the site's own metadata.

What is covered comes from Walkthrough Settings: the chosen modules (by
default every module of the installed apps - ERPNext included - except
Frappe's own: users, roles, system settings),
narrowed - by default - to what the workspace sidebars actually list, since
that is what people can reach. The workspace becomes the category.

For each DocType in scope:
  Create a <DocType>         interactive: the viewer fills each key field,
                             then everything else required, saves, submits
  Find and read a <DocType>  the list, its filters, a record, its tabs
For each report in scope:
  Read the <Report> report   filters, columns, export

Captions are built in every language from Walkthrough Settings (see i18n).
"""

import re

import frappe
from frappe.utils import strip_html

from frappe_walkthrough.i18n import T, languages, split

LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold", "Image"}
CORE_APPS = {"frappe"}          # its own modules: users, roles, settings
SKIP_FIELDS = {"naming_series", "amended_from", "company", "currency"}

# Every sentence the generator writes. Translations: i18n/<lang>.json.
TEMPLATES = [
	"{0}: {1}",
	"This is the {0} list.",
	"Add opens a new {0}.",
	"Choose the {0}.",
	"Set the {0}.",
	"Add the {0} - one row for each.",
	"Tick {0} if it applies.",
	"Attach the {0}.",
	"Enter the {0}.",
	"Now anything else the form needs.",
	"Save it as a draft.",
	"Submit it to make it final. A submitted document is changed by cancelling and amending it.",
	"Save it.",
	"Create a {0}",
	"A new {0}, field by field.",
	"The {0} list - every record, newest first.",
	"Narrow it with the filters along the top.",
	"Each row is one {0}. Click it to open it.",
	"Opening one.",
	"The head names it and shows where it has got to.",
	"The {0} tab.",
	"Find and read a {0}",
	"Where every {0} is kept and how to read one.",
	"The {0} report.",
	"Set the filters along the top - the figures follow as soon as one changes.",
	"Click a column heading to sort by it; drag its edge to widen it.",
	"Export, print or pick the columns from the menu.",
	"Read the {0} report",
	"What the {0} report shows.",
	"Find your way around",
	"The sidebar, the search bar and this button - everything else starts from these.",
	"The sidebar lists the workspaces and what is in each.",
	"Search finds any list, report or record by name - press Ctrl + K from anywhere.",
	"Walkthrough is on every page. It lists what can be done on that page first, then everything else.",
	"Getting around",
	# process walkthroughs (processes.py)
	"From {0} to {1}",
	"Make a {0} and carry it through: {1}.",
	"Start with a new {0}.",
	"Now the {0}: Create → {1} carries everything over from the {2}.",
	"That is the whole chain, each document made from the one before.",
]

# Interface strings of the panel and player (walkthrough.js), sent per language.
UI = [
	"Walkthroughs", "Walkthrough", "On this page", "All walkthroughs", "Filter…", "Ask how to do something…",
	"Ask", "Thinking…", "Not sure - is it this one?", "No walkthrough covers that yet.",
	"The assistant is unreachable right now.", "Pause", "Play", "Next", "Stop", "interactive", "steps",
	"Type it, then press Enter", "Type it, then press Ctrl + Enter", "Choose an option", "Tick it or press Next",
	"Type it or pick it from the calendar, then press Enter", "Add the rows, then press Next",
	"Press Save, or Ctrl + S", "Press Submit, then confirm", "Saved as {0}.",
	"Saved as {0}. Submit it when it is ready to go.", "Submitted: {0}.",
	"Save it first - there is nothing to submit yet.", "{0} is required.",
	"That is it. Open Walkthrough again for another.", "Open {0} from the sidebar.", "Open the {0} group.",
	"{0} is not in the sidebar - search for it by name.", "Type its name and pick it from the results.",
	"Nothing to show here yet.", "Process", "Create", "Read", "Report", "Board", "Tour", "Language",
	"Record a walkthrough", "Recording", "steps", "Stop and save", "Cancel", "Title", "Category", "Kind", "Summary",
	"Caption", "Write the captions", "Save walkthrough", "Draft",
	"Throw this recording away?",
	"Save and submit it first - then Create → {0} appears.",
	"Open {0}.",
	"Add a new {0}.",
	"Open a {0}.",
	"Choose the {0}.",
	"Set the {0}.",
	"Add the {0}.",
	"Enter the {0}.",
	"Save it.",
	"Submit it.",
	"Create → {0}.",
	"The {0} tab.",
	"Press {0}.",
	"One plain sentence. The Ask box matches questions against it.",
	"Steps",
	"Action",
	"Target",
	"Saved. It is in the Walkthrough panel now.",
]


def slug(name):
	return frappe.scrub(name).replace("_", "-")


def S(action, sentence, **kw):
	"""A step: `sentence` is {lang: text} from T()."""
	say, tr = split(sentence)
	d = {"action": action, "say": say, "translations": tr or None}
	d.update({k: v for k, v in kw.items() if v is not None})
	return d


def W(key, kind, category, title, summary, contexts, steps, **kw):
	t_en, t_tr = split(title)
	s_en, s_tr = split(summary)
	translations = {}
	for lang in set(t_tr) | set(s_tr):
		translations[lang] = {"title": t_tr.get(lang, t_en), "summary": s_tr.get(lang, s_en)}
	d = {"key": key, "kind": kind, "category": category, "title": t_en, "summary": s_en,
	     "contexts": "\n".join(c for c in contexts if c), "steps": steps, "translations": translations or None}
	d.update(kw)
	return d


# ------------------------------------------------------------------ scope

def _settings():
	return frappe.get_cached_doc("Walkthrough Settings")


def modules(s=None):
	s = s or _settings()
	chosen = {r.module for r in (s.get("modules") or []) if r.module}
	rows = frappe.get_all("Module Def", fields=["name", "app_name"])
	if not chosen:
		chosen = {r.name for r in rows if r.app_name not in CORE_APPS and r.app_name != "frappe_walkthrough"}
	if s.get("include_core"):
		chosen |= {r.name for r in rows if r.app_name in CORE_APPS}
	return chosen


def _table_exists(dt):
	try:
		return frappe.db.table_exists(dt)
	except Exception:
		return False


def workspace_listings():
	"""[(link_type, link_to, workspace)] from every public workspace sidebar,
	link card and shortcut - v16 sidebars first, then v15-style links."""
	out = []
	if _table_exists("Workspace Sidebar Item"):
		out += [(r.link_type, r.link_to, r.ws) for r in frappe.db.sql(
			"""select i.link_type, i.link_to, s.title ws from `tabWorkspace Sidebar Item` i
			join `tabWorkspace Sidebar` s on s.name = i.parent
			where i.link_type in ('DocType', 'Report') and ifnull(i.link_to, '') != ''
			  and ifnull(s.for_user, '') = '' order by s.creation, i.idx""", as_dict=True)]
	ws_filter = "and ifnull(w.public, 1) = 1" if frappe.get_meta("Workspace").has_field("public") else ""
	out += [(r.link_type, r.link_to, r.ws) for r in frappe.db.sql(
		f"""select l.link_type, l.link_to, w.name ws from `tabWorkspace Link` l
		join `tabWorkspace` w on w.name = l.parent
		where l.type = 'Link' and l.link_type in ('DocType', 'Report') and ifnull(l.link_to, '') != ''
		  and ifnull(l.hidden, 0) = 0 {ws_filter} order by w.sequence_id, l.idx""", as_dict=True)]
	out += [(r.type, r.link_to, r.ws) for r in frappe.db.sql(
		f"""select s.type, s.link_to, w.name ws from `tabWorkspace Shortcut` s
		join `tabWorkspace` w on w.name = s.parent
		where s.type in ('DocType', 'Report') and ifnull(s.link_to, '') != '' {ws_filter}
		order by w.sequence_id, s.idx""", as_dict=True)]
	return out


def scope(s=None):
	"""{"doctypes": [(doctype, category)], "reports": [(report, category)]}"""
	s = s or _settings()
	mods = modules(s)
	excluded = {r.doctype_name for r in (s.get("exclude_doctypes") or [])}
	extra = [r.doctype_name for r in (s.get("extra_doctypes") or []) if r.doctype_name]
	dt_rows = {r.name: r for r in frappe.get_all(
		"DocType", fields=["name", "module", "istable", "issingle", "is_virtual"], limit_page_length=0)}
	rp_rows = {r.name: r for r in frappe.get_all(
		"Report", filters={"disabled": 0, "report_type": ["in", ["Query Report", "Script Report"]]},
		fields=["name", "module", "ref_doctype"], limit_page_length=0)}

	def dt_ok(dt):
		r = dt_rows.get(dt)
		return r and not r.istable and not r.is_virtual and r.module in mods and dt not in excluded \
			and r.module != "Frappe Walkthrough"

	def rp_ok(rp):
		r = rp_rows.get(rp)
		return r and r.module in mods

	doctypes, reports, seen = [], [], set()
	listed = workspace_listings()
	for kind, name, ws in listed:
		if (kind, name) in seen:
			continue
		if kind == "DocType" and dt_ok(name):
			seen.add((kind, name)); doctypes.append((name, ws))
		elif kind == "Report" and rp_ok(name):
			seen.add((kind, name)); reports.append((name, ws))
	if not s.get("only_in_workspaces", 1) or not listed:
		for dt, r in sorted(dt_rows.items()):
			if ("DocType", dt) not in seen and dt_ok(dt):
				seen.add(("DocType", dt)); doctypes.append((dt, r.module))
		for rp, r in sorted(rp_rows.items()):
			if ("Report", rp) not in seen and rp_ok(rp):
				seen.add(("Report", rp)); reports.append((rp, r.module))
	ws_of = {name: ws for _k, name, ws in listed}
	for dt in extra:
		if ("DocType", dt) not in seen and dt in dt_rows and dt not in excluded:
			seen.add(("DocType", dt)); doctypes.append((dt, ws_of.get(dt) or dt_rows[dt].module))
	# an app can group its records its own way (walkthrough_categories hook)
	cats = hook_categories()
	if cats:
		doctypes = [(dt, cats.get(dt) or cats.get(cat) or cat) for dt, cat in doctypes]
		reports = [(rp, cats.get(rp) or cats.get(cat) or cat) for rp, cat in reports]
	return {"doctypes": doctypes, "reports": reports}


def hook_categories():
	"""{DocType, Report or workspace name: category} from the walkthrough_categories hook."""
	out = {}
	for path in frappe.get_hooks("walkthrough_categories"):
		try:
			out.update(frappe.get_attr(path)() or {})
		except Exception:
			frappe.log_error(title=f"walkthrough_categories: {path}")
	return out


# ------------------------------------------------------------------ words

def _in_languages(d):
	"""Only the languages captions are built in; English always."""
	langs = set(languages())
	return {k: v for k, v in d.items() if k == "en" or k in langs}


def _with(label_of, text_of):
	"""'{label}: {text}' in each language of `text_of`."""
	return {k: f"{label_of.get(k, label_of['en'])}: {v}" for k, v in text_of.items()}


def summary_of(doctype, hooks=None):
	"""A one-line summary: an app's own (walkthrough_summaries hook), the
	DocType's description, or nothing."""
	got = (hooks or {}).get(doctype)
	if got:
		return _in_languages(got)
	desc = strip_html(frappe.get_meta(doctype).description or "").strip()
	desc = re.sub(r"\s+", " ", desc)
	return {"en": desc} if desc and len(desc) <= 200 else None


def hook_summaries():
	out = {}
	for path in frappe.get_hooks("walkthrough_summaries"):
		try:
			out.update(frappe.get_attr(path)() or {})
		except Exception:
			frappe.log_error(title=f"walkthrough_summaries: {path}")
	return out


def _ask_for(df):
	t = df.fieldtype
	if t in ("Link", "Dynamic Link", "Select"):
		tpl = "Choose the {0}."
	elif t in ("Date", "Datetime", "Time"):
		tpl = "Set the {0}."
	elif t in ("Table", "Table MultiSelect"):
		tpl = "Add the {0} - one row for each."
	elif t == "Check":
		tpl = "Tick {0} if it applies."
	elif t in ("Attach", "Attach Image"):
		tpl = "Attach the {0}."
	else:
		tpl = "Enter the {0}."
	sentence = T(tpl, df.label or df.fieldname)
	desc = re.sub(r"\s+", " ", strip_html(df.description or "")).strip()
	if desc and len(desc) <= 140:
		extra = T(desc)
		sentence = {k: f"{v} {extra.get(k, desc)}" for k, v in sentence.items()}
	return sentence


def key_fields(meta, limit):
	"""What a person has to fill on a new one, in form order."""
	out = []
	for df in meta.fields:
		if df.fieldtype in LAYOUT or not df.reqd or df.hidden or df.read_only:
			continue
		if df.fetch_from or df.fieldname in SKIP_FIELDS or df.default not in (None, ""):
			continue
		out.append(df)
	return out[:limit]


def tabs(meta):
	return [df.label for df in meta.fields if df.fieldtype == "Tab Break" and df.label][:4]


def can_be_created(meta):
	return not (meta.issingle or meta.istable or meta.get("in_create") or meta.get("is_virtual"))


# ------------------------------------------------------------------ builders

def create_walkthrough(doctype, category, limit=6, summaries=None):
	meta = frappe.get_meta(doctype)
	info = summary_of(doctype, summaries)
	first = _with(T("{0}", doctype), info) if info else T("This is the {0} list.", doctype)
	steps = [S("go", first, route=slug(doctype)), S("new", T("Add opens a new {0}.", doctype), ref_doctype=doctype)]
	for df in key_fields(meta, limit):
		steps.append(S("input", _ask_for(df), target=f"field:{df.fieldname}"))
	steps.append(S("fill", T("Now anything else the form needs.")))
	if meta.is_submittable:
		steps.append(S("save", T("Save it as a draft.")))
		steps.append(S("submit", T("Submit it to make it final. A submitted document is changed by cancelling and amending it.")))
	else:
		steps.append(S("save", T("Save it.")))
	return W(f"create-{slug(doctype)}", "Create", category, T("Create a {0}", doctype),
	         info or T("A new {0}, field by field.", doctype), [f"DocType:{doctype}", f"Workspace:{category}"], steps,
	         source_doctype=doctype)


def read_walkthrough(doctype, category, summaries=None):
	meta = frappe.get_meta(doctype)
	if meta.issingle:
		steps = [S("go", T("{0}", doctype), route=slug(doctype))]
	else:
		steps = [
			S("go", T("The {0} list - every record, newest first.", doctype), route=slug(doctype)),
			S("point", T("Narrow it with the filters along the top."), target="filters"),
			S("point", T("Each row is one {0}. Click it to open it.", doctype), target="row"),
			S("open", T("Opening one."), ref_doctype=doctype),
			S("point", T("The head names it and shows where it has got to."), target="title"),
		]
	for tab in tabs(meta):
		steps.append(S("tab", T("The {0} tab.", tab), label=tab))
	info = summary_of(doctype, summaries)
	if info:
		steps.append(S("say", info))
	return W(f"read-{slug(doctype)}", "Read", category, T("Find and read a {0}", doctype),
	         T("Where every {0} is kept and how to read one.", doctype), [f"DocType:{doctype}"], steps,
	         source_doctype=doctype)


def report_walkthrough(report, category, summaries=None):
	info = _in_languages((summaries or {}).get(report) or {}) or None
	first = _with(T("{0}", report), info) if info else T("The {0} report.", report)
	steps = [
		S("go", first, route=f"query-report/{report}"),
		S("point", T("Set the filters along the top - the figures follow as soon as one changes."), target="report-filters"),
		S("point", T("Click a column heading to sort by it; drag its edge to widen it."), target="report-table"),
		S("point", T("Export, print or pick the columns from the menu."), target="menu"),
	]
	return W(f"report-{slug(report)}", "Report", category, T("Read the {0} report", report),
	         info or T("What the {0} report shows.", report), [f"Report:{report}"], steps, source_report=report)


def tour():
	"""The one walkthrough every site gets."""
	return W("find-your-way-around", "Tour", T("Getting around")["en"], T("Find your way around"),
	         T("The sidebar, the search bar and this button - everything else starts from these."),
	         ["Page:home", "Workspace:Home"], [
		         S("point", T("The sidebar lists the workspaces and what is in each."), target="sidebar"),
		         S("point", T("Search finds any list, report or record by name - press Ctrl + K from anywhere."), target="search"),
		         S("point", T("Walkthrough is on every page. It lists what can be done on that page first, then everything else."),
		           target="css:.wt-btn"),
	         ], sort_order=1)


def generated(s=None):
	"""Every walkthrough the settings call for, in order."""
	s = s or _settings()
	sc = scope(s)
	summaries = hook_summaries()
	limit = s.get("max_inputs") or 6
	no_create = {r.doctype_name for r in (s.get("no_create_doctypes") or [])}
	out = [tour()] if s.get("include_tour", 1) else []
	n = 0
	for dt, cat in sc["doctypes"]:
		try:
			meta = frappe.get_meta(dt)
			if s.get("include_create", 1) and can_be_created(meta) and dt not in no_create:
				n += 1; out.append({**create_walkthrough(dt, cat, limit, summaries), "sort_order": 100 + n})
			if s.get("include_read", 1):
				n += 1; out.append({**read_walkthrough(dt, cat, summaries), "sort_order": 100 + n})
		except Exception:
			frappe.log_error(title=f"Walkthrough: could not build for {dt}")
	if s.get("include_reports", 1):
		for rp, cat in sc["reports"]:
			n += 1; out.append({**report_walkthrough(rp, cat, summaries), "sort_order": 100 + n})
	return out
