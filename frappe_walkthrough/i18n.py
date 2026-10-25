"""Languages and words.

Every caption is stored in English (`say`) plus a `translations` map
{lang: text}. Generated captions are put together from a sentence template
and a label ("Choose the {0}." + "Customer"), each translated on its own:

  1. terms an app supplies through the `walkthrough_terms` hook
     ({lang: {"Customer": "…"}}) - for its own vocabulary;
  2. this app's sentence and interface translations, i18n/<lang>.json;
  3. Frappe's own translations - which already cover every DocType name,
     field label and tab label of every installed app in every language
     Frappe ships;
  4. otherwise the English.

Missing sentence translations can be filled by the Writer (any provider) when
Load runs; they are kept per site in private/walkthrough_i18n.json, and the
shipped i18n/<lang>.json files are never touched.
"""

import json
import os

import frappe

HERE = os.path.dirname(__file__)
CACHE_TERMS = "walkthrough:terms"


def _memo():
	"""Per-request memo: a Load builds thousands of sentences."""
	if not hasattr(frappe.local, "walkthrough_memo"):
		frappe.local.walkthrough_memo = {}
	return frappe.local.walkthrough_memo


def languages():
	"""The languages captions are built in, English first."""
	m = _memo()
	if "langs" not in m:
		m["langs"] = _languages()
	return m["langs"]


def _languages():
	s = frappe.get_cached_doc("Walkthrough Settings")
	langs = [r.language for r in (s.get("languages") or []) if r.language]
	if not langs:
		langs = [frappe.db.get_single_value("System Settings", "language") or "en"]
		langs += frappe.get_all("User", filters={"enabled": 1, "user_type": "System User", "language": ["is", "set"]},
		                        pluck="language", distinct=True)
	out = ["en"]
	for lang in langs:
		lang = (lang or "").strip()
		if lang and lang not in out:
			out.append(lang)
	return out


def base(lang):
	return (lang or "en").split("-")[0].lower()


_app_dicts = {}


def _app_dict(lang):
	"""This app's sentence + interface translations for a language."""
	if lang not in _app_dicts:
		d = {}
		for name in (lang, base(lang)):
			p = os.path.join(HERE, "i18n", f"{name}.json")
			if os.path.exists(p):
				with open(p, encoding="utf-8") as f:
					d = {**json.load(f), **d}
		extra = _written().get(lang)
		if extra:
			d = {**extra, **d}
		_app_dicts[lang] = d
	return _app_dicts[lang]


def _hook_terms():
	m = _memo()
	if "terms" in m:
		return m["terms"]
	terms = frappe.cache().get_value(CACHE_TERMS)
	if terms is None:
		terms = {}
		for path in frappe.get_hooks("walkthrough_terms"):
			try:
				got = frappe.get_attr(path)()
			except Exception:
				frappe.log_error(title=f"walkthrough_terms: {path}")
				continue
			for lang, d in (got or {}).items():
				terms.setdefault(lang, {}).update(d or {})
		frappe.cache().set_value(CACHE_TERMS, terms, expires_in_sec=3600)
	m["terms"] = terms
	return terms


def tr(text, lang):
	"""A word, label or sentence in `lang`."""
	if not text or base(lang) == "en":
		return text
	m = _memo().setdefault("tr", {})
	k = (lang, text)
	if k not in m:
		m[k] = _tr(text, lang)
	return m[k]


def _tr(text, lang):
	terms = _hook_terms()
	for name in (lang, base(lang)):
		got = (terms.get(name) or {}).get(text)
		if got:
			return got
	got = _app_dict(lang).get(text)
	if got:
		return got
	try:
		got = frappe._(text, lang=lang)
	except TypeError:          # very old signature
		got = None
	return got or text


def T(template, *args):
	"""A sentence in every language: {"en": ..., "ar": ...}. Arguments are
	labels, each translated on its own."""
	out = {}
	for lang in languages():
		tpl = tr(template, lang)
		try:
			out[lang] = tpl.format(*[tr(a, lang) for a in args])
		except (IndexError, KeyError):
			out[lang] = template.format(*args)
	return out


def split(d):
	"""(english, {lang: text}) for storing in say + translations."""
	d = dict(d)
	en = d.pop("en", "")
	return en, {k: v for k, v in d.items() if v and v != en}


def missing_templates(langs=None):
	"""Sentences with no translation, per language - for the Writer to fill."""
	from frappe_walkthrough.generator import TEMPLATES
	out = {}
	for lang in langs or languages():
		if base(lang) == "en":
			continue
		have = _app_dict(lang)
		todo = [t for t in TEMPLATES if t not in have]
		if todo:
			out[lang] = todo
	return out


def _written_path():
	return frappe.get_site_path("private", "walkthrough_i18n.json")


def _written():
	p = _written_path()
	if os.path.exists(p):
		with open(p, encoding="utf-8") as f:
			return json.load(f)
	return {}


def store_written(lang, mapping):
	"""Writer translations of this app's sentences, kept for this site."""
	cur = _written()
	cur.setdefault(lang, {}).update(mapping)
	with open(_written_path(), "w", encoding="utf-8") as f:
		json.dump(cur, f, ensure_ascii=False, indent=1)
	_app_dicts.pop(lang, None)
	_memo().pop("tr", None)


def ui_strings(lang):
	"""The interface strings of the panel and player, for the browser."""
	from frappe_walkthrough.generator import UI
	return {s: tr(s, lang) for s in UI}
