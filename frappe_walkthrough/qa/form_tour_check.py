"""Import a throwaway Form Tour, check the walkthrough it becomes, remove both.

    bench --site <site> execute frappe_walkthrough.qa.form_tour_check.run --kwargs '{"doctype": "Customer"}'
"""

import json

import frappe


def run(doctype="Customer"):
	from frappe_walkthrough import loader
	frappe.set_user("Administrator")
	meta = frappe.get_meta(doctype)
	field = next(df for df in meta.fields if df.reqd and df.fieldtype not in ("Section Break", "Column Break", "Tab Break"))
	ft = frappe.get_doc({"doctype": "Form Tour", "title": "WT import check", "reference_doctype": doctype,
	                     "module": meta.module, "steps": [
		                     {"title": field.label, "description": "<p>Where the name goes.</p>", "fieldname": field.fieldname},
		                     {"title": "Save", "description": "Then save it.", "element_selector": ".primary-action"}]})
	ft.flags.ignore_validate = True
	ft.insert(ignore_permissions=True)
	key = None
	try:
		n = loader.import_form_tours()
		key = "form-tour-" + frappe.scrub(ft.name).replace("_", "-")
		w = frappe.get_doc("Walkthrough", key)
		print("IMPORTED", n, "|", w.title, "|", w.kind, w.source, w.category, "|", w.contexts)
		for s in w.steps:
			print("   ", s.action, s.target or s.route or s.ref_doctype or "", "|", s.say)
		# a hand edit survives a re-import
		w.steps[-1].say = "Edited by hand."
		w.save(ignore_permissions=True)
		loader.import_form_tours()
		w.reload()
		print("EDITED KEPT:", w.is_edited == 1 and w.steps[-1].say == "Edited by hand.")
	finally:
		if key and frappe.db.exists("Walkthrough", key):
			frappe.delete_doc("Walkthrough", key, ignore_permissions=True, force=True)
		frappe.delete_doc("Form Tour", ft.name, ignore_permissions=True, force=True)
		frappe.db.commit()
		print("CLEANED", not frappe.db.exists("Form Tour", ft.name), not (key and frappe.db.exists("Walkthrough", key)))
