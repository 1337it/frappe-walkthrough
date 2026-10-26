import frappe


def run():
	for dt in ("Sales Order", "Rental Quotation", "Chauffeur Booking", "Quotation"):
		m = frappe.get_meta(dt)
		try:
			d = m.get_dashboard_data()
			print(dt, "DASH", [(t.get("label"), t.get("items")) for t in (d.transactions or [])][:6], "| fieldname:", d.fieldname)
		except Exception as e:
			print(dt, "DASH ERR", e)
