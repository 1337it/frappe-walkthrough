"""Print the document chains the process finder sees (nothing is written).

    bench --site <site> execute frappe_walkthrough.qa.process_check.run --kwargs '{"app": "erpnext"}'
"""

import frappe


def run(app=None, limit=40):
	from frappe_walkthrough import generator, processes
	frappe.set_user("Administrator")
	if app:
		mods = frappe.get_all("Module Def", filters={"app_name": app}, pluck="name")
		dts = frappe.get_all("DocType", filters={"module": ["in", mods], "istable": 0, "issingle": 0}, pluck="name")
	else:
		dts = [d for d, _c in generator.scope(frappe.get_doc("Walkthrough Settings"))["doctypes"]]
	g = processes.edges(dts)
	print("DOCTYPES", len(dts), "WITH CREATE EDGES", len(g), "EDGES", sum(len(v) for v in g.values()))
	found = processes.chains(dts, limit=80)
	print("CANDIDATES", len(found))
	for c in processes.choose(found, limit=limit):
		print("  " + "  →  ".join([c[0][0]] + [f"[{x[1]}] {x[0]}" for x in c[1:]]))
