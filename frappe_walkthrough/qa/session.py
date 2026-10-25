"""A desk session for browser tests: prints a sid.

    bench --site <site> execute frappe_walkthrough.qa.session.sid
"""

import frappe


def sid(user="Administrator"):
	from frappe.sessions import Session
	from werkzeug.test import EnvironBuilder
	from werkzeug.wrappers import Request
	frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
	frappe.local.request_ip = "127.0.0.1"
	s = Session(user=user, resume=False, full_name=user, user_type="System User")
	frappe.db.commit()
	print("SID", s.sid)
	return s.sid


def end(sid):
	frappe.db.delete("Sessions", {"sid": sid})
	frappe.db.commit()
