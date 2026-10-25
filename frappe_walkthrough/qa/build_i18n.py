"""For maintainers: (re)build the shipped translations in i18n/<lang>.json
with the Writer configured on a site. Only missing strings are asked for.

    bench --site <site> execute frappe_walkthrough.qa.build_i18n.run --kwargs '{"langs": ["fr", "de"]}'
"""

import json
import os

import frappe

from frappe_walkthrough import i18n, writer
from frappe_walkthrough.generator import TEMPLATES, UI

OUT = os.path.join(os.path.dirname(i18n.__file__), "i18n")


def run(langs=None):
	langs = langs or sorted(f[:-5] for f in os.listdir(OUT) if f.endswith(".json"))
	texts = list(dict.fromkeys(TEMPLATES + UI))
	for lang in langs:
		path = os.path.join(OUT, f"{lang}.json")
		have = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
		todo = [t for t in texts if t not in have]
		if not todo:
			print(lang, "complete")
			continue
		got = writer.translate(todo, lang, kind="interface strings and caption templates of a guided tour in a business system")
		got = {k: v for k, v in got.items() if k.count("{0}") == v.count("{0}") and k.count("{1}") == v.count("{1}")}
		have.update(got)
		with open(path, "w", encoding="utf-8") as f:
			json.dump(dict(sorted(have.items())), f, ensure_ascii=False, indent=1)
			f.write("\n")
		print(lang, len(have), "/", len(texts))
