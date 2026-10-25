"""Check the Writer against this site's settings.

    bench --site <site> execute frappe_walkthrough.qa.writer_check.run
"""

import time

import frappe


def run():
	from frappe_walkthrough import api, writer
	frappe.set_user("Administrator")
	t = time.time()
	print("TEST", api.test_writer(), f"{time.time() - t:.1f}s")
	t = time.time()
	print("TRANSLATE", writer.translate(["Choose the {0}.", "Plate Code", "Rental Agreement"], "ml"), f"{time.time() - t:.1f}s")
	t = time.time()
	print("AGAIN (from memory)", writer.translate(["Choose the {0}.", "Plate Code", "Rental Agreement"], "ml"), f"{time.time() - t:.2f}s")
