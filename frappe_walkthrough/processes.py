"""Process walkthroughs: following a chain of documents from one to the next.

Most hand-written walkthroughs follow a business chain - quotation, order,
delivery, invoice, payment. Frappe already describes those chains:

  - a DocType's dashboard lists the documents made from it
    (Sales Order -> Delivery Note, Sales Invoice, Payment Entry);
  - its form script adds a Create button for each
    (frm.add_custom_button(__("Delivery Note"), ..., __("Create")));
  - the next document links back to it (Rental Reservation.quotation).

This module finds those chains among the DocTypes in scope and builds a
walkthrough for each: the first document made field by field, saved,
submitted, then Create -> the next one, and so on. The steps come from code,
so every target is real; the Writer, when configured, only chooses which key
fields to stop at and writes the words. Without a Writer the captions come
from the same templates the generated walkthroughs use.

Process walkthroughs are saved as drafts (switched off) unless Walkthrough
Settings says to switch them on: an admin plays them, edits them and switches
them on. Once edited, Load leaves them alone.
"""

import os
import re

import frappe
from frappe.utils import strip_html

from frappe_walkthrough import generator
from frappe_walkthrough.i18n import T, languages, split, tr

MAX_CHAIN = 5          # documents in one process
MAX_PROCESSES = 40
GROUPS = ("Create", "Make")

# its sentences are listed in generator.TEMPLATES, for the translations


# ------------------------------------------------------------------ what the code says

def _js_files(doctype):
	"""The form scripts of a DocType: its own, and any an app adds (doctype_js)."""
	meta = frappe.get_meta(doctype)
	out = []
	app = frappe.local.module_app.get(frappe.scrub(meta.module))
	if app:
		p = frappe.get_app_path(app, frappe.scrub(meta.module), "doctype", frappe.scrub(doctype), frappe.scrub(doctype) + ".js")
		if os.path.exists(p):
			out.append(p)
	for a in frappe.get_installed_apps():
		hooked = frappe.get_hooks("doctype_js", app_name=a)
		paths = hooked.get(doctype) if isinstance(hooked, dict) else None
		for path in ([paths] if isinstance(paths, str) else paths or []):
			p = frappe.get_app_path(a, path)
			if os.path.exists(p):
				out.append(p)
	return out


_BTN = re.compile(r"add_custom_button\s*\(")
_LABEL = re.compile(r"""__\(\s*["']([^"']{2,60})["']\s*\)""")


def create_buttons(doctype):
	"""[(label, group, code)] of the buttons under Create / Make on this form."""
	out = []
	for p in _js_files(doctype):
		try:
			src = open(p, encoding="utf-8").read()
		except OSError:
			continue
		starts = [m.end() for m in _BTN.finditer(src)]
		for i, st in enumerate(starts):
			chunk = src[st: (starts[i + 1] if i + 1 < len(starts) else st + 800)][:800]
			labels = _LABEL.findall(chunk)
			if len(labels) >= 2 and labels[-1] in GROUPS and labels[0] not in GROUPS:
				out.append((labels[0], labels[-1], chunk))
	seen, uniq = set(), []
	for label, group, code in out:
		if (label, group) not in seen:
			seen.add((label, group)); uniq.append((label, group, code))
	return uniq


def _links_back():
	"""{doctype: {doctypes that have a Link field to it}}"""
	rows = frappe.db.sql("""select parent, options from tabDocField where fieldtype = 'Link'
		and parent not in (select name from tabDocType where istable = 1)""", as_dict=True)
	rows += frappe.db.sql("""select dt parent, options from `tabCustom Field` where fieldtype = 'Link'""", as_dict=True)
	out = {}
	for r in rows:
		out.setdefault(r.options, set()).add(r.parent)
	return out


def _dashboard(doctype):
	try:
		d = frappe.get_meta(doctype).get_dashboard_data()
		return {it for t in (d.transactions or []) for it in (t.get("items") or [])}
	except Exception:
		return set()


def _match(label, candidates, code=""):
	"""The DocType a Create button makes: 'Delivery Note' or 'Reservation' ->
	'Rental Reservation'; 'Payment' -> Payment Entry, by the method its code
	calls (make_payment_entry)."""
	low = label.lower().strip()
	for c in candidates:
		if c.lower() == low:
			return c
	ends = [c for c in candidates if c.lower().endswith(" " + low)]
	has = [c for c in candidates if low in c.lower()]
	pool = ends if len(ends) == 1 else has
	if len(pool) == 1:
		return pool[0]
	named = [c for c in (ends or has) if frappe.scrub(c) in code]
	return named[0] if len(named) == 1 else None


def edges(doctypes):
	"""{A: [(B, label, group)]}: B is made from A by the Create button `label`."""
	allowed = set(doctypes)
	back = _links_back()
	out = {}
	for a in doctypes:
		cands = (_dashboard(a) | back.get(a, set())) & allowed
		cands.discard(a)
		if not cands:
			continue
		for label, group, code in create_buttons(a):
			b = _match(label, sorted(cands), code)
			if b and b != a:
				out.setdefault(a, []).append((b, label, group))
	return out


def _weights(doctypes):
	"""How much each DocType matters here: the rows the site already has (a
	count, nothing more), else how prominently the workspaces show it."""
	import math
	rows = {r.t[3:]: r.n or 0 for r in frappe.db.sql(
		"""select table_name t, table_rows n from information_schema.tables
		where table_schema = database() and table_name like 'tab%%'""", as_dict=True)}
	shortcuts = {r[1] for r in generator.workspace_listings() if r[0] == "DocType"}
	short2 = set(frappe.get_all("Workspace Shortcut", filters={"type": "DocType"}, pluck="link_to"))
	out = {}
	for dt in doctypes:
		w = math.log1p(rows.get(dt, 0))
		w += 1.0 if dt in short2 else 0.5 if dt in shortcuts else 0
		w += 0.5 if frappe.get_meta(dt).is_submittable else 0
		out[dt] = w
	return out


def chains(doctypes, max_len=MAX_CHAIN, limit=MAX_PROCESSES, per_start=2):
	"""The chains worth a walkthrough: [[(doctype, label, group), ...]].

	Every simple path of 2..max_len documents is scored by how much its
	documents matter here (_weights); then, best first, a path is kept when
	it adds a step not already covered and is not part of a kept one - so a
	handful of chains covers the graph instead of fifty variations of one."""
	g = edges(doctypes)
	wt = _weights({x for a, nxt in g.items() for x in [a] + [b for b, _l, _g in nxt]})
	paths = []

	def walk(path):
		if len(path) >= 2:
			paths.append(list(path))
		if len(path) >= max_len:
			return
		cur = path[-1][0]
		for b, label, group in g.get(cur, []):
			if b not in {p[0] for p in path}:
				walk(path + [(b, label, group)])

	for a in g:
		walk([(a, None, None)])

	def score(p):
		return sum(wt.get(x[0], 0) for x in p) / (len(p) ** 0.35)

	paths.sort(key=lambda p: (-score(p), -len(p)))
	kept, covered, starts = [], set(), {}
	sig = lambda p: tuple(x[0] for x in p)
	for p in paths:
		steps = {(p[i][0], p[i + 1][0]) for i in range(len(p) - 1)}
		if not steps - covered:
			continue
		if starts.get(p[0][0], 0) >= per_start:
			continue
		if any(_inside(sig(p), sig(k)) for k in kept):
			continue
		kept.append(p)
		covered |= steps
		starts[p[0][0]] = starts.get(p[0][0], 0) + 1
		if len(kept) >= limit:
			break
	return kept


def _inside(small, big):
	n = len(small)
	return any(big[i:i + n] == small for i in range(len(big) - n + 1))


# ------------------------------------------------------------------ the walkthrough

def _fields_for_writer(doctype, limit=14):
	meta = frappe.get_meta(doctype)
	out = []
	for df in meta.fields:
		if df.fieldtype in generator.LAYOUT or df.hidden or df.read_only or df.fetch_from:
			continue
		if df.fieldname in generator.SKIP_FIELDS:
			continue
		if df.reqd or df.in_list_view or df.bold or df.in_standard_filter:
			out.append({"fieldname": df.fieldname, "label": df.label, "type": df.fieldtype, "required": bool(df.reqd)})
	return out[:limit]


def build(chain, category, words=None, limit=4):
	"""The walkthrough for one chain. `words` is the Writer's answer, if any:
	{title, summary, docs: [{doctype, intro, fields: [{fieldname, say}]}], outro}."""
	words = words or {}
	by_dt = {d.get("doctype"): d for d in (words.get("docs") or []) if isinstance(d, dict)}
	names = [c[0] for c in chain]
	first = names[0]
	steps = [generator.S("go", T("This is the {0} list.", first), route=generator.slug(first))]
	for i, (dt, label, group) in enumerate(chain):
		meta = frappe.get_meta(dt)
		w = by_dt.get(dt) or {}
		if i == 0:
			intro = _sentence(w.get("intro")) or T("Start with a new {0}.", dt)
			steps.append(generator.S("new", intro, ref_doctype=dt))
		else:
			prev = names[i - 1]
			intro = _sentence(w.get("intro")) or T("Now the {0}: Create → {1} carries everything over from the {2}.", dt, label, prev)
			steps.append(generator.S("make", intro, target=f"menu:{group}/{label}", ref_doctype=dt))
		# the fields to stop at: the Writer's pick, else the generator's key fields
		real = {df.fieldname: df for df in meta.fields}
		picked = []
		for f in w.get("fields") or []:
			fn = (f or {}).get("fieldname")
			df = real.get(fn)
			if df and df.fieldtype not in generator.LAYOUT and not df.hidden and not df.read_only and fn not in [p[0].fieldname for p in picked]:
				picked.append((df, _sentence(f.get("say"))))
		if not picked:
			picked = [(df, None) for df in generator.key_fields(meta, limit)]
		for df, say in picked[:limit]:
			steps.append(generator.S("input", say or generator._ask_for(df), target=f"field:{df.fieldname}"))
		steps.append(generator.S("fill", T("Now anything else the form needs.")))
		if meta.is_submittable:
			steps.append(generator.S("save", T("Save it as a draft.")))
			steps.append(generator.S("submit", T("Submit it to make it final. A submitted document is changed by cancelling and amending it.")))
		else:
			steps.append(generator.S("save", T("Save it.")))
	steps.append(generator.S("say", _sentence(words.get("outro")) or T("That is the whole chain, each document made from the one before.")))
	title = _sentence(words.get("title")) or T("From {0} to {1}", first, names[-1])
	chain_text = " → ".join(names)
	summary = _sentence(words.get("summary")) or {lang: tr("Make a {0} and carry it through: {1}.", lang).format(
		tr(first, lang), " → ".join(tr(n, lang) for n in names)) for lang in languages()}
	key = "process-" + "-".join(generator.slug(n) for n in names)[:120]
	return generator.W(key, "Process", category, title, summary,
	                   [f"DocType:{n}" for n in names] + [f"Workspace:{category}"], steps, source_doctype=first)


def _sentence(text):
	"""Writer text (English) as {en: ...}; translated later with everything else."""
	text = strip_html(str(text or "")).strip()
	return {"en": text} if text else None


# ------------------------------------------------------------------ the Writer's part

def words_for(chain, category):
	"""Ask the Writer to pick the key fields and write the words. None if it cannot."""
	from frappe_walkthrough import writer
	if not writer.configured():
		return None
	mem = writer._memory()
	key = "process:" + "|".join(c[0] for c in chain)
	if key in mem:
		return mem[key]
	summaries = generator.hook_summaries()
	docs = []
	for i, (dt, label, group) in enumerate(chain):
		meta = frappe.get_meta(dt)
		about = (summaries.get(dt) or {}).get("en") or strip_html(meta.description or "").strip()
		docs.append({"doctype": dt, "made_from_previous_by": f"{group} → {label}" if label else None,
		             "about": about[:300], "submittable": bool(meta.is_submittable), "fields": _fields_for_writer(dt)})
	try:
		got = writer.complete(
			"You write guided walkthroughs for a business system. The walkthrough follows a chain of documents, each "
			"made from the one before with the Create button. For the chain given, return: `title` (short, e.g. "
			"'From quotation to invoice'), `summary` (one plain sentence saying what it teaches, in the words its "
			"users would use - people will search for it by asking 'how do I …'), and for each document in `docs`: "
			"`doctype` (exactly as given), `intro` (one sentence: why this document, said to the person making it), "
			"`fields` (2 to 4 of the given fields worth stopping at - the ones that matter to the business, by "
			"`fieldname` exactly as given - each with `say`, one short instruction), and finally `outro` (one "
			"sentence). Plain, warm, no marketing. Use only fieldnames from the lists.",
			{"category": category, "docs": docs})
	except Exception:
		frappe.log_error(title="Walkthrough writer: process words")
		return None
	if got and got.get("docs"):
		mem[key] = got
		writer._remember(mem)
	return got


# ------------------------------------------------------------------ during Load

def choose(candidates, limit=MAX_PROCESSES):
	"""With a Writer: the chains a business really follows, from the candidates
	(a Create button can lead somewhere rarely used - an inter-company receipt,
	a blanket order). Without one: the candidates as scored."""
	from frappe_walkthrough import writer
	if not writer.configured() or len(candidates) <= 3:
		return candidates[:limit]
	mem = writer._memory()
	listing = [" → ".join(x[0] for x in c) for c in candidates]
	key = "choose:" + "|".join(listing)
	picked = mem.get(key)
	if picked is None:
		try:
			got = writer.complete(
				"These are chains of documents in a business system, each made from the one before with its Create "
				"button. Pick the ones that are processes a business really follows day to day and that someone "
				"would want shown - e.g. quotation → order → delivery → invoice → payment. Leave out chains through "
				"rarely used or unusual documents, and near-duplicates (prefer the longer, more complete one). "
				f"Return `picked`: the indexes, best first, at most {limit}.",
				{"chains": [{"index": i, "chain": t} for i, t in enumerate(listing)]})
			picked = [int(i) for i in (got.get("picked") or []) if str(i).isdigit() and int(i) < len(candidates)]
		except Exception:
			frappe.log_error(title="Walkthrough writer: choose processes")
			picked = []
		if picked:
			mem[key] = picked
			writer._remember(mem)
	return [candidates[i] for i in picked][:limit] if picked else candidates[:limit]


def generated(s, sc=None, progress=None):
	"""Process walkthroughs for the DocTypes in scope."""
	sc = sc or generator.scope(s)
	cat_of = dict(sc["doctypes"])
	out = []
	found = choose(chains(list(cat_of), limit=80))
	for i, ch in enumerate(found):
		if progress:
			progress(f"Processes {i + 1}/{len(found)}")
		cat = cat_of.get(ch[0][0]) or ""
		try:
			words = words_for(ch, cat)
			w = build(ch, cat, words)
		except Exception:
			frappe.log_error(title=f"Walkthrough: process {[c[0] for c in ch]}")
			continue
		w["source"] = "AI" if words else "Generated"
		w["draft"] = not s.get("processes_live")
		w["sort_order"] = 50 + i
		out.append(w)
	return out
