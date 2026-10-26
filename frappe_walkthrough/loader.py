"""Load: writes every walkthrough the settings call for into the Walkthrough
DocType - the generated ones, and those other apps ship.

An app ships walkthroughs by naming a function in its hooks.py:

    walkthroughs = ["my_app.walkthroughs.get"]

returning a list of dicts - {key, title, kind, category, summary, contexts,
steps: [{action, target | route | ref_doctype | label | text, say}]}. Any
language can be given alongside: title_ar / summary_ar on the walkthrough,
say_ar on a step (or a `translations` dict, as stored).

Rules: a walkthrough edited by hand is never overwritten; one this code wrote
before and no longer produces is switched off, never deleted.
"""

import json

import frappe
from frappe.utils import now_datetime

from frappe_walkthrough import generator, i18n

STATUS = "walkthrough:load_status"
FIELDS = ("title", "category", "kind", "summary", "contexts", "sort_order", "source_doctype", "source_report")


def status():
	return frappe.cache().get_value(STATUS) or {}


def _progress(**kw):
	cur = status()
	cur.update(kw)
	frappe.cache().set_value(STATUS, cur, expires_in_sec=24 * 3600)
	frappe.publish_realtime("walkthrough_load", cur, user=cur.get("user"), after_commit=False)


def enqueue(user=None):
	if status().get("running"):
		return status()
	_progress(running=1, done=0, total=0, phase="Starting", user=user or frappe.session.user, error=None,
	          started=str(now_datetime()))
	frappe.enqueue("frappe_walkthrough.loader.run", queue="long", timeout=3600, user=user or frappe.session.user)
	return status()


# ------------------------------------------------------------------ from apps

def _norm(w, app):
	"""An app's walkthrough in the stored shape."""
	w = dict(w)
	tr = dict(w.get("translations") or {})
	for k in list(w):
		for part in ("title", "summary"):
			if k.startswith(part + "_") and len(k) <= len(part) + 6:
				lang = k[len(part) + 1:]
				tr.setdefault(lang, {})[part] = w.pop(k)
	w["translations"] = tr or None
	if isinstance(w.get("contexts"), (list, tuple)):
		w["contexts"] = "\n".join(w["contexts"])
	steps = []
	for st in w.get("steps") or []:
		st = dict(st)
		if "do" in st and "action" not in st:
			st["action"] = st.pop("do")
		str_ = dict(st.get("translations") or {})
		for k in list(st):
			if k.startswith("say_"):
				str_[k[4:]] = st.pop(k)
		st["translations"] = str_ or None
		if st.get("route"):
			st["route"] = strip_prefix(st["route"])
		steps.append(st)
	w["steps"] = steps
	w["source"] = "App"
	w["source_app"] = app
	return w


def strip_prefix(route):
	"""'/desk/sales-order' or '/app/sales-order' -> 'sales-order'."""
	r = str(route or "").strip()
	for p in ("/desk/", "/app/", "desk/", "app/"):
		if r.startswith(p):
			return r[len(p):]
	return r.lstrip("/")


def from_apps():
	out = []
	for app in frappe.get_installed_apps():
		for path in frappe.get_hooks("walkthroughs", app_name=app):
			try:
				for w in frappe.get_attr(path)() or []:
					out.append(_norm(w, app))
			except Exception:
				frappe.log_error(title=f"walkthroughs hook: {path}")
	return out


# ------------------------------------------------------------------ writing

def upsert(w):
	name = w["key"]
	if frappe.db.exists("Walkthrough", name):
		doc = frappe.get_doc("Walkthrough", name)
		if doc.is_edited:
			return "kept"
		# switched off by an earlier Load (no longer produced then) and produced again:
		# back on - drafts excepted, and anything switched off by hand is marked edited above
		if not doc.enabled and not w.get("draft"):
			doc.enabled = 1
	else:
		doc = frappe.new_doc("Walkthrough")
		doc.key = name
		# a draft starts switched off; after that, on or off is the admin's call
		doc.enabled = 0 if w.get("draft") else 1
	for f in FIELDS:
		if f in w:
			doc.set(f, w[f])
	doc.source = w.get("source") or "Generated"
	doc.source_app = w.get("source_app")
	doc.translations = json.dumps(w["translations"], ensure_ascii=False) if w.get("translations") else None
	doc.set("steps", [])
	for st in w["steps"]:
		row = {k: st.get(k) for k in ("action", "target", "route", "ref_doctype", "label", "text", "say")}
		row["translations"] = json.dumps(st["translations"], ensure_ascii=False) if st.get("translations") else None
		doc.append("steps", row)
	doc.flags.from_load = True
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)
	return "written"


def run(user=None):
	"""The background job behind the Load button."""
	try:
		frappe.flags.in_walkthrough_load = True
		i18n._app_dicts.clear()
		frappe.local.walkthrough_memo = {}
		s = frappe.get_doc("Walkthrough Settings")
		_progress(phase="Reading what to cover", running=1, error=None, counts=None, done=0, total=0)
		from frappe_walkthrough import writer
		if writer.configured(s) and s.ai_translations:
			_progress(phase="Translating sentences and labels")
			writer.fill_templates()
			writer.fill_terms(generator.scope(s))
		ws = generator.generated(s)
		if s.get("include_processes", 1):
			from frappe_walkthrough import processes
			ws += processes.generated(s, progress=lambda ph: _progress(phase=ph))
		ws += from_apps()
		if writer.configured(s):
			_progress(phase="Writing summaries and translations")
			writer.improve(ws, s)
		_progress(phase="Saving", total=len(ws), done=0)
		counts, seen = {}, set()
		for i, w in enumerate(ws):
			try:
				r = upsert(w)
			except Exception:
				frappe.log_error(title=f"Walkthrough: could not save {w.get('key')}")
				r = "failed"
			counts[r] = counts.get(r, 0) + 1
			seen.add(w["key"])
			if i % 20 == 0:
				frappe.db.commit()
				_progress(done=i + 1)
		stale = frappe.get_all("Walkthrough", filters={"source": ["in", ["Generated", "App", "AI"]], "enabled": 1,
		                                               "is_edited": 0, "name": ["not in", list(seen) or [""]]}, pluck="name")
		for n in stale:
			frappe.db.set_value("Walkthrough", n, "enabled", 0, update_modified=False)
		frappe.db.commit()
		clear_cache()
		_progress(running=0, phase="Done", done=len(ws), counts=counts, disabled=len(stale), finished=str(now_datetime()))
	except Exception as exc:
		frappe.db.rollback()
		frappe.log_error(title="Walkthrough: Load failed")
		_progress(running=0, phase="Failed", error=str(exc)[:300])
	finally:
		frappe.flags.in_walkthrough_load = False


def clear_cache():
	frappe.cache().delete_value("walkthrough:catalogue")
	frappe.cache().delete_value(i18n.CACHE_TERMS)
	frappe.cache().delete_keys("walkthrough:catalogue:")


def remove_generated():
	names = frappe.get_all("Walkthrough", filters={"source": ["in", ["Generated", "AI"]], "is_edited": 0}, pluck="name")
	for n in names:
		frappe.delete_doc("Walkthrough", n, ignore_permissions=True, force=True)
	clear_cache()
	return len(names)


# ------------------------------------------------------------------ Form Tours

def import_form_tours():
	"""Frappe's own Form Tours as walkthroughs (pointing, no clicks)."""
	n = 0
	for ft in frappe.get_all("Form Tour", pluck="name"):
		t = frappe.get_doc("Form Tour", ft)
		steps = []
		if t.reference_doctype and not t.ui_tour:
			steps.append({"action": "go", "route": generator.slug(t.reference_doctype), "say": t.title})
			steps.append({"action": "new" if t.get("new_document_form") or not t.first_document else "open",
			              "ref_doctype": t.reference_doctype, "say": t.title})
		elif t.get("page_route"):
			steps.append({"action": "go", "route": strip_prefix(t.page_route), "say": t.title})
		for st in t.steps:
			text = " ".join(x for x in (st.title, frappe.utils.strip_html(st.description or "")) if x).strip()
			if st.fieldname and not st.is_table_field:
				steps.append({"action": "point", "target": f"field:{st.fieldname}", "say": text})
			elif st.element_selector:
				steps.append({"action": "point", "target": f"css:{st.element_selector}", "say": text})
			else:
				steps.append({"action": "say", "say": text})
		if not steps:
			continue
		ctx = [f"DocType:{t.reference_doctype}"] if t.reference_doctype else []
		w = {"key": f"form-tour-{generator.slug(ft)}", "title": t.title or ft, "kind": "Tour",
		     "category": t.module or (frappe.db.get_value("DocType", t.reference_doctype, "module") if t.reference_doctype else "Getting around"),
		     "summary": t.title, "contexts": "\n".join(ctx), "steps": steps, "source": "Form Tour", "translations": None}
		upsert(w)
		n += 1
	frappe.db.commit()
	clear_cache()
	return n
