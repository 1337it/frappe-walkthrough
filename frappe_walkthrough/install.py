"""Out of the box: settings with sensible defaults, and a first Load."""

import frappe


def ensure_role():
	"""Walkthrough Manager: records and edits walkthroughs without being a System Manager."""
	if not frappe.db.exists("Role", "Walkthrough Manager"):
		frappe.get_doc({"doctype": "Role", "role_name": "Walkthrough Manager", "desk_access": 1}).insert(ignore_permissions=True)


def after_install():
	ensure_role()
	s = frappe.get_doc("Walkthrough Settings")
	s.flags.ignore_mandatory = True
	s.save(ignore_permissions=True)          # stores the defaults
	frappe.db.commit()
	frappe.cache().delete_key("bootinfo")     # so the button appears without a re-login
	from frappe_walkthrough import loader
	loader.enqueue(user="Administrator")


def fill_new_defaults():
	"""Settings saved before a newer version added an option have it empty;
	give each such option its default (a new tick box defaulting to on, say)."""
	meta = frappe.get_meta("Walkthrough Settings")
	stored = set(frappe.db.sql_list("select field from tabSingles where doctype = 'Walkthrough Settings'"))
	if not stored:
		return
	for df in meta.fields:
		if df.fieldname not in stored and df.default not in (None, "") and df.fieldtype not in ("Button", "HTML", "Table MultiSelect"):
			frappe.db.set_single_value("Walkthrough Settings", df.fieldname, df.default)
	frappe.clear_cache(doctype="Walkthrough Settings")


def after_migrate():
	ensure_role()
	fill_new_defaults()
	frappe.cache().delete_value("walkthrough:catalogue")
