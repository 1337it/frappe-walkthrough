"""What the desk needs at login: whether to show the button, the design, and
the interface strings in the user's language."""

import frappe

from frappe_walkthrough import i18n

SPEED = {"Slow": 1.5, "Normal": 1.0, "Fast": 0.6}


def boot_session(bootinfo):
	if frappe.session.user == "Guest":
		return
	try:
		s = frappe.get_cached_doc("Walkthrough Settings")
	except Exception:
		return
	roles = {r.role for r in (s.get("roles") or []) if r.role}
	show = bool(s.show_button) and (not roles or bool(roles & set(frappe.get_roles())))
	lang = frappe.local.lang or "en"
	langs = i18n.languages()
	names = dict(frappe.get_all("Language", filters={"name": ["in", langs]}, fields=["name", "language_name"],
	                            as_list=True))
	bootinfo.walkthrough = {
		"show": show,
		"label": s.button_label or "Walkthrough",
		"on": {"workspace": s.on_workspaces, "list": s.on_lists, "form": s.on_forms, "report": s.on_reports,
		       "page": s.on_pages},
		"panel_side": (s.panel_side or "Right").lower(),
		"speed": SPEED.get(s.speed or "Normal", 1.0),
		"reduced_motion": s.reduced_motion or "Follow the device",
		"design": {
			"accent": s.accent_color or "#2563eb", "font": s.font_family or "", "panel_width": s.panel_width or 400,
			"cursor": s.cursor_color or "#1b1c1e", "cursor_size": s.cursor_size or 26,
			"ring": s.ring_color or s.accent_color or "#2563eb", "dim": (s.dim_percent if s.dim_percent is not None else 14) / 100.0,
			"caption_bg": s.caption_bg or "#1b1c1e", "caption_text": s.caption_text or "#ffffff",
			"caption_width": s.caption_width or 340, "radius": s.radius if s.radius is not None else 12,
		},
		"languages": [{"code": l, "name": names.get(l) or l} for l in langs],
		"lang": lang,
		"ui": i18n.ui_strings(lang),
		"rtl": lang.split("-")[0] in ("ar", "he", "fa", "ur", "ps", "sd", "ug", "yi"),
		"can_record": bool({"System Manager", "Walkthrough Manager"} & set(frappe.get_roles())),
		"writer": bool(s.writer_provider and s.writer_model),
	}
