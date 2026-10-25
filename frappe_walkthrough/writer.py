"""The Writer: any language model, used only while Load runs.

Providers: OpenAI, Azure OpenAI, Anthropic, or any OpenAI-compatible endpoint
(Ollama, vLLM, OpenRouter, LiteLLM, …). It is asked for JSON and never sees a
user's data - only DocType names, field labels and captions.

What it does, each part only when there is something missing:
  - translates this app's sentences into languages it does not ship;
  - translates labels Frappe has no translation for (custom apps' own words);
  - writes a one-line summary where a DocType has no description;
  - translates captions of hand-written walkthroughs.
Every answer is kept for the site (private/walkthrough_ai.json), so running
Load again costs nothing for what is already known.
"""

import json
import os
import re

import frappe
import requests

from frappe_walkthrough import i18n

BATCH = 60


def configured(s=None):
	s = s or frappe.get_cached_doc("Walkthrough Settings")
	return bool(s.writer_provider and s.writer_model and s.get_password("writer_api_key", raise_exception=False))


# ------------------------------------------------------------------ the call

def complete(system, payload, s=None, timeout=120):
	"""The model's JSON answer to `payload`, as a dict."""
	s = s or frappe.get_cached_doc("Walkthrough Settings")
	provider, model = s.writer_provider, s.writer_model
	key = s.get_password("writer_api_key", raise_exception=False)
	user = json.dumps(payload, ensure_ascii=False)
	system = system + "\nAnswer with one JSON object only."
	if provider == "Anthropic":
		r = requests.post("https://api.anthropic.com/v1/messages", timeout=timeout, headers={
			"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
			json={"model": model, "max_tokens": 8000, "system": system, "messages": [{"role": "user", "content": user}]})
		_raise(r)
		text = "".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text")
	else:
		if provider == "OpenAI":
			url, headers = "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}
		elif provider == "Azure OpenAI":
			base = (s.writer_base_url or "").rstrip("/")
			base = base if base.startswith("http") else f"https://{base}"
			url, headers = f"{base}/openai/v1/chat/completions", {"api-key": key}
		else:
			base = (s.writer_base_url or "").rstrip("/")
			url, headers = f"{base}/chat/completions", {"Authorization": f"Bearer {key}"}
		body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
		        "response_format": {"type": "json_object"}}
		r = requests.post(url, json=body, headers=headers, timeout=timeout)
		if r.status_code == 400 and "response_format" in r.text:
			body.pop("response_format")
			r = requests.post(url, json=body, headers=headers, timeout=timeout)
		_raise(r)
		text = r.json()["choices"][0]["message"]["content"] or ""
	return _json(text)


def _raise(r):
	if r.status_code >= 300:
		raise Exception(f"{r.status_code}: {r.text[:300]}")


def _json(text):
	text = text.strip()
	text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
	try:
		return json.loads(text)
	except ValueError:
		m = re.search(r"\{.*\}", text, re.S)
		return json.loads(m.group(0)) if m else {}


def test():
	out = complete("You translate short UI labels.", {"translate_to": "French", "items": ["Save", "Customer"],
	                                                    "return": {"items": [{"en": "...", "tr": "..."}]}})
	return out


# ------------------------------------------------------------------ memory

def _path():
	return frappe.get_site_path("private", "walkthrough_ai.json")


def _memory():
	p = _path()
	if os.path.exists(p):
		with open(p, encoding="utf-8") as f:
			return json.load(f)
	return {}


def _remember(mem):
	with open(_path(), "w", encoding="utf-8") as f:
		json.dump(mem, f, ensure_ascii=False, indent=0)


LANG_NAMES = {}


def _lang_name(lang):
	if lang not in LANG_NAMES:
		LANG_NAMES[lang] = frappe.db.get_value("Language", lang, "language_name") or lang
	return LANG_NAMES[lang]


def translate(texts, lang, kind="UI labels and short sentences of a business system"):
	"""{english: translation} for each text, from memory or the model."""
	mem = _memory()
	k = f"tr:{lang}:"
	out = {t: mem[k + t] for t in texts if k + t in mem}
	todo = [t for t in dict.fromkeys(texts) if t and k + t not in mem]
	for i in range(0, len(todo), BATCH):
		chunk = todo[i:i + BATCH]
		try:
			got = complete(
				f"Translate {kind} into {_lang_name(lang)} ({lang}), the way people in an office would say them. "
				"Keep placeholders like {0} and {1} exactly. Keep product names, codes and abbreviations as they are. "
				"Return every item, with `en` exactly as given.",
				{"items": chunk, "return": {"items": [{"en": "...", "tr": "..."}]}})
		except Exception:
			frappe.log_error(title=f"Walkthrough writer: translate to {lang}")
			break
		for it in got.get("items") or []:
			if it.get("en") in chunk and (it.get("tr") or "").strip():
				out[it["en"]] = mem[k + it["en"]] = it["tr"].strip()
		_remember(mem)
	return out


# ------------------------------------------------------------------ during Load

def fill_templates():
	"""This app's sentences and interface strings, for languages it does not ship."""
	from frappe_walkthrough.generator import TEMPLATES, UI
	for lang in i18n.languages():
		if i18n.base(lang) == "en":
			continue
		have = i18n._app_dict(lang)
		todo = [t for t in TEMPLATES + UI if t not in have]
		if todo:
			got = translate(todo, lang)
			if got:
				i18n.store_written(lang, got)


def fill_terms(sc):
	"""Labels in scope that Frappe cannot translate - typically a custom app's."""
	from frappe_walkthrough import generator
	terms = set()
	for dt, cat in sc["doctypes"]:
		terms |= {dt, cat}
		meta = frappe.get_meta(dt)
		terms |= {df.label for df in generator.key_fields(meta, 12) if df.label}
		terms |= set(generator.tabs(meta))
	for rp, cat in sc["reports"]:
		terms |= {rp, cat}
	terms = sorted(t for t in terms if t)
	for lang in i18n.languages():
		if i18n.base(lang) == "en":
			continue
		todo = [t for t in terms if i18n.tr(t, lang) == t]
		if todo:
			got = translate(todo, lang, kind="names of records, fields and screens in a business system")
			if got:
				i18n.store_written(lang, got)


def summaries(items):
	"""One-line summaries for DocTypes/reports that have none: {name: text}."""
	mem = _memory()
	out = {n: mem["sum:" + n] for n, _ in items if "sum:" + n in mem}
	todo = [(n, about) for n, about in items if "sum:" + n not in mem]
	for i in range(0, len(todo), 25):
		chunk = todo[i:i + 25]
		try:
			got = complete(
				"For each record type or report of a business system, write ONE plain sentence (max 20 words) saying "
				"what it is for, in the words its users would use. Do not start with 'This'. No marketing.",
				{"items": [{"name": n, "about": a} for n, a in chunk],
				 "return": {"items": [{"name": "...", "summary": "..."}]}})
		except Exception:
			frappe.log_error(title="Walkthrough writer: summaries")
			break
		for it in got.get("items") or []:
			if it.get("name") and (it.get("summary") or "").strip():
				out[it["name"]] = mem["sum:" + it["name"]] = it["summary"].strip()
		_remember(mem)
	return out


def improve(ws, s):
	"""Summaries where there were none, then translations of anything still English."""
	langs = [l for l in i18n.languages() if i18n.base(l) != "en"]
	if s.ai_summaries:
		need = []
		for w in ws:
			name = w.get("source_doctype") or w.get("source_report")
			if not name or w.get("source") == "App":
				continue
			if w["summary"].startswith(("A new ", "Where every ", "What the ")):
				if w.get("source_doctype"):
					meta = frappe.get_meta(name)
					about = f"module {meta.module}; fields: " + ", ".join(
						df.label for df in meta.fields if df.label and df.fieldtype not in ("Section Break", "Column Break", "Tab Break"))[:400]
				else:
					about = "report in module " + (frappe.db.get_value("Report", name, "module") or "")
				need.append((name, about))
		got = summaries(list(dict.fromkeys(need)))
		for w in ws:
			name = w.get("source_doctype") or w.get("source_report")
			if name in got and w["summary"].startswith(("A new ", "Where every ", "What the ")):
				w["summary"] = got[name]
				tr = w.get("translations") or {}
				for lang in langs:
					tr.setdefault(lang, {})["summary"] = got[name]       # translated below
				w["translations"] = tr
	if not s.ai_translations or not langs:
		return
	for lang in langs:
		texts = set()
		for w in ws:
			tr = (w.get("translations") or {}).get(lang) or {}
			for part in ("title", "summary"):
				if not tr.get(part) or tr.get(part) == w.get(part):
					texts.add(w.get(part) or "")
			for st in w["steps"]:
				if st.get("say") and not (st.get("translations") or {}).get(lang):
					texts.add(st["say"])
		texts.discard("")
		if not texts:
			continue
		got = translate(sorted(texts), lang, kind="captions of a guided tour of a business system")
		for w in ws:
			tr = w.get("translations") or {}
			cur = tr.setdefault(lang, {})
			for part in ("title", "summary"):
				if (not cur.get(part) or cur.get(part) == w.get(part)) and w.get(part) in got:
					cur[part] = got[w[part]]
			w["translations"] = tr
			for st in w["steps"]:
				if st.get("say") in got and not (st.get("translations") or {}).get(lang):
					st["translations"] = {**(st.get("translations") or {}), lang: got[st["say"]]}
