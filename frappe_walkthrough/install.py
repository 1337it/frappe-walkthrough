"""Out of the box: settings with sensible defaults, and a first Load."""

import frappe


def after_install():
	s = frappe.get_doc("Walkthrough Settings")
	s.flags.ignore_mandatory = True
	s.save(ignore_permissions=True)          # stores the defaults
	frappe.db.commit()
	frappe.cache().delete_key("bootinfo")     # so the button appears without a re-login
	from frappe_walkthrough import loader
	loader.enqueue(user="Administrator")


def after_migrate():
	frappe.cache().delete_value("walkthrough:catalogue")
