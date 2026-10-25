"""A walkthrough the desk plays with an animated cursor (public/js/walkthrough.js).

Generated and app-shipped ones are written by Load (frappe_walkthrough.loader).
Editing one here marks it as edited, and Load then leaves it alone.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

NEEDS = {
	"target": ("input", "point", "click", "type"),
	"route": ("go",),
	"ref_doctype": ("open", "new"),
	"label": ("tab",),
}


class Walkthrough(Document):
	def validate(self):
		if not self.flags.from_load and not self.is_new() and self.source in ("Generated", "App", "Form Tour"):
			self.is_edited = 1
		for row in self.steps:
			for field, actions in NEEDS.items():
				if row.action in actions and not row.get(field):
					frappe.throw(_("Row {0}: a {1} step needs {2}.").format(row.idx, row.action, _(self.meta_label(field))))
		for field in ("translations",):
			_check_json(self.get(field), _("Translations"))
		for row in self.steps:
			_check_json(row.translations, _("Row {0} translations").format(row.idx))

	@staticmethod
	def meta_label(field):
		return {"target": "Target", "route": "Route", "ref_doctype": "DocType", "label": "Tab label"}[field]

	def on_update(self):
		_clear()

	def on_trash(self):
		_clear()


def _check_json(value, what):
	if not value:
		return
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("{0} must be JSON, like {1}").format(what, '{"ar": "…"}'))
	if not isinstance(value, dict):
		frappe.throw(_("{0} must be JSON, like {1}").format(what, '{"ar": "…"}'))


def _clear():
	if not frappe.flags.in_walkthrough_load:
		frappe.cache().delete_value("walkthrough:catalogue")
