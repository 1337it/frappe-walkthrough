"""What the browser calls."""

import json

import frappe
import requests

from frappe_walkthrough import i18n, loader

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MAX = 254          # Jev answers a choice among at most 255 options (one is NONE)


def _settings():
	return frappe.get_cached_doc("Walkthrough Settings")


def _lang(lang=None):
	return lang or frappe.local.lang or "en"


def _pick(base, translations, lang, part=None):
	if i18n.base(lang) == "en" or not translations:
		return base
	if isinstance(translations, str):
		try:
			translations = json.loads(translations)
		except ValueError:
			return base
	for name in (lang, i18n.base(lang)):
		got = translations.get(name)
		if got:
			return (got.get(part) if part else got) or base
	return base


def _rows():
	"""Every enabled walkthrough, without its steps."""
	rows = frappe.cache().get_value("walkthrough:catalogue")
	if rows is None:
		rows = frappe.get_all("Walkthrough", filters={"enabled": 1}, limit_page_length=0,
		                      fields=["name", "title", "category", "kind", "summary", "contexts", "sort_order",
		                              "source_doctype", "source_report", "translations"],
		                      order_by="sort_order asc, title asc")
		counts = {r.parent: r.n for r in frappe.db.sql(
			"select parent, count(*) n from `tabWalkthrough Step` group by parent", as_dict=True)}
		for r in rows:
			r["steps_count"] = counts.get(r.name, 0)
			r["contexts"] = [c.strip() for c in (r.contexts or "").splitlines() if c.strip()]
		frappe.cache().set_value("walkthrough:catalogue", rows, expires_in_sec=3600)
	return rows


def _allowed(r, memo):
	"""Only what this user can do: create walkthroughs need create permission."""
	dt = r.get("source_doctype")
	if dt:
		ptype = "create" if r["kind"] == "Create" else "read"
		k = (dt, ptype)
		if k not in memo:
			memo[k] = bool(frappe.has_permission(dt, ptype))
		return memo[k]
	rp = r.get("source_report")
	if rp:
		k = ("Report", rp)
		if k not in memo:
			memo[k] = bool(frappe.has_permission("Report", "read", rp))
		return memo[k]
	return True


def _visible(lang):
	memo, out = {}, []
	for r in _rows():
		if not _allowed(r, memo):
			continue
		out.append({
			"key": r.name, "kind": r.kind, "category": r.category or "",
			"category_label": i18n.tr(r.category or "", lang),
			"title": _pick(r.title, r.translations, lang, "title"),
			"summary": _pick(r.summary or "", r.translations, lang, "summary"),
			"title_en": r.title, "summary_en": r.summary or "",
			"contexts": r["contexts"], "steps_count": r["steps_count"],
		})
	return out


@frappe.whitelist()
def catalogue(context=None, workspace=None, lang=None):
	"""On-page walkthroughs first, then everything by category."""
	lang = _lang(lang)
	items = _visible(lang)
	cats, order = {}, []
	for it in items:
		if it["category"] not in cats:
			cats[it["category"]] = {"name": it["category"], "label": it["category_label"], "items": []}
			order.append(it["category"])
		cats[it["category"]]["items"].append(it)
	home = None
	if context and context.startswith("Workspace:"):
		home = context.split(":", 1)[1]
	if workspace:
		home = workspace
	if not home and context:
		home = next((it["category"] for it in items if context in it["contexts"]), None)
	s = _settings()
	return {
		"context": context, "on_page": [it for it in items if context and context in it["contexts"]],
		"categories": [cats[c] for c in order], "home_category": home if home in cats else None,
		"ai": bool(s.enable_ask and _jev_key()), "total": len(items),
	}


@frappe.whitelist()
def get(key, lang=None):
	"""One walkthrough, with its steps, in the viewer's language."""
	lang = _lang(lang)
	doc = frappe.get_doc("Walkthrough", key)
	if not doc.enabled:
		frappe.throw(frappe._("This walkthrough is switched off."))
	return {
		"key": doc.name, "kind": doc.kind, "category": doc.category,
		"title": _pick(doc.title, doc.translations, lang, "title"),
		"steps": [{"action": s.action, "target": s.target, "route": loader.strip_prefix(s.route) if s.route else None,
		           "ref_doctype": s.ref_doctype, "label": s.label, "text": s.text,
		           "say": _pick(s.say or "", s.translations, lang)} for s in doc.steps],
	}


@frappe.whitelist()
def ui(lang=None):
	return i18n.ui_strings(_lang(lang))


# ------------------------------------------------------------------ Ask

def _jev_key():
	s = _settings()
	return s.get_password("jev_key", raise_exception=False) or frappe.conf.get("jev_key")


def _jev(state, criteria, key, timeout=6):
	body = {"model": "jev-latest", "state": state, "questions": {"walkthrough": {
		"type": "choice", "criteria": criteria,
		"instructions": "Which walkthrough shows how to do what `user_asked` asks? Prefer one that matches "
		                "`current_page` only when two fit equally well. If none of them does, pick NONE."}}}
	r = requests.post(JEV_URL, json=body, timeout=timeout, headers={"Authorization": f"Bearer {key}"})
	r.raise_for_status()
	a = r.json()["answers"]["walkthrough"]
	return a.get("choice"), float(a.get("confidence") or 0)


def _pool(items, context, home):
	"""At most JEV_MAX walkthroughs: this page's, this workspace's, then the
	ones that do something, then the rest."""
	ranked = ([it for it in items if context and context in it["contexts"]]
	          + [it for it in items if home and it["category"] == home]
	          + [it for it in items if it["kind"] in ("Process", "Tour", "Board", "Create")]
	          + items)
	seen, out = set(), []
	for it in ranked:
		if it["key"] not in seen:
			seen.add(it["key"]); out.append(it)
		if len(out) >= JEV_MAX:
			break
	return out


@frappe.whitelist()
def ask(question, context=None, workspace=None, lang=None):
	"""Jev picks the walkthrough that answers the question, or says none does."""
	s = _settings()
	key = _jev_key()
	question = (question or "").strip()
	if not (s.enable_ask and key and question):
		return {"key": None, "confidence": 0}
	lang = _lang(lang)
	items = _visible(lang)
	home = workspace or (context.split(":", 1)[1] if context and context.startswith("Workspace:") else None)
	pool = _pool(items, context, home)
	by_key = {it["key"]: it for it in pool}
	criteria = {it["key"]: f'[{it["category"]}] {it["title_en"]}: {it["summary_en"]}' for it in pool}
	criteria["NONE"] = "None of these is what the user is asking about"
	site = frappe.db.get_single_value("System Settings", "app_name") or "this business system"
	state = {"user_asked": question[:500], "current_page": context or "",
	         "note": f"A user of {site} asking, in any language, how to do something. Pick the walkthrough that shows them how."}
	try:
		choice, conf = _jev(state, criteria, key)
	except Exception as exc:
		frappe.log_error(title="Walkthrough: Jev", message=str(exc)[:500])
		return {"key": None, "confidence": 0, "error": True}
	if choice == "NONE" or choice not in by_key:
		return {"key": None, "confidence": conf}
	if conf < (s.min_confidence or 0.6):
		return {"key": None, "confidence": conf, "guess": choice, "item": by_key[choice]}
	return {"key": choice, "confidence": conf, "item": by_key[choice]}


# ------------------------------------------------------------------ settings page actions

def _admin():
	frappe.only_for("System Manager")


@frappe.whitelist()
def load():
	_admin()
	return loader.enqueue()


@frappe.whitelist()
def load_status():
	_admin()
	st = loader.status()
	st["counts_now"] = {r.source: r.n for r in frappe.db.sql(
		"select source, count(*) n from `tabWalkthrough` where enabled = 1 group by source", as_dict=True)}
	st["edited"] = frappe.db.count("Walkthrough", {"is_edited": 1})
	return st


@frappe.whitelist()
def remove_generated():
	_admin()
	return loader.remove_generated()


@frappe.whitelist()
def import_form_tours():
	_admin()
	return loader.import_form_tours()


@frappe.whitelist()
def test_jev():
	_admin()
	key = _jev_key()
	if not key:
		return {"ok": False, "message": frappe._("No Jev API key yet.")}
	try:
		choice, conf = _jev({"user_asked": "how do I add a new customer?"},
		                    {"a": "Create a Customer", "b": "Read the General Ledger report", "NONE": "None of these"}, key, timeout=10)
		return {"ok": choice == "a", "message": frappe._("Jev answered {0} ({1:.0%} sure).").format(choice, conf)}
	except Exception as exc:
		return {"ok": False, "message": str(exc)[:300]}


@frappe.whitelist()
def test_writer():
	_admin()
	from frappe_walkthrough import writer
	if not writer.configured():
		return {"ok": False, "message": frappe._("Choose a provider and model and enter the API key first.")}
	try:
		got = writer.test()
		items = got.get("items") or []
		return {"ok": bool(items), "message": ", ".join(f'{i.get("en")} → {i.get("tr")}' for i in items) or json.dumps(got)[:200]}
	except Exception as exc:
		return {"ok": False, "message": str(exc)[:300]}
