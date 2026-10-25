import frappe
from frappe.model.document import Document


class WalkthroughSettings(Document):
	def validate(self):
		if self.min_confidence and not (0 < self.min_confidence <= 1):
			frappe.throw(frappe._("The confidence must be between 0 and 1."))
		if self.dim_percent is not None and not (0 <= self.dim_percent <= 80):
			frappe.throw(frappe._("Dimming must be between 0 and 80 percent."))

	def on_update(self):
		# the design and the button reach the browser at login
		frappe.cache().delete_key("bootinfo")
		frappe.cache().delete_value("walkthrough:catalogue")
