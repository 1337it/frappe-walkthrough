/* Typed dates were being thrown away.

   Every Date and Datetime field in the desk lost the first characters typed
   into it - type "20-12-2026 10:00" and the box held "-12-2026 10:00", which
   is not a date, so the field stayed empty (or a Date field complained the
   value was not dd-mm-yyyy). Only picking from the calendar worked.

   The cause is in Frappe's date control (controls/date.js). Each time the
   calendar pops up it is repositioned through update_datepicker_position,
   which calls the picker's update(); air-datepicker's update() rewrites the
   input with whatever date is SELECTED in the calendar - nothing, while you
   are still typing - so whatever had been typed so far was wiped. The popup
   shows on focus and again as the first keys land, so anyone who clicks and
   starts typing lost the start of the date. On a field that already held a
   date it put the old date back over the edit.

   The fix keeps the repositioning and puts the typed text straight back. It
   is a patch on the prototype rather than an edit to Frappe, so it survives
   a Frappe update, and it covers every date field in every app on the desk,
   forms and dialogs alike.

   ControlDate lives in Frappe's controls bundle, which loads after this one,
   so the patch is applied as soon as the class exists.
*/
frappe.provide("frappe_walkthrough");

frappe_walkthrough.patch_date_typing = function () {
	const Control = frappe.ui && frappe.ui.form && frappe.ui.form.ControlDate;
	if (!Control) return false;
	const proto = Control.prototype;
	if (proto.__wt_keeps_typing) return true;

	const reposition = proto.update_datepicker_position;
	if (typeof reposition !== "function") return true; // nothing to fix in this version

	proto.update_datepicker_position = function () {
		const $input = this.$input;
		const typed = $input ? $input.val() : null;
		const out = reposition.apply(this, arguments);
		if ($input && typed !== null && $input.val() !== typed) {
			$input.val(typed);
		}
		return out;
	};
	proto.__wt_keeps_typing = true;
	return true;
};

(function apply_when_ready() {
	if (frappe_walkthrough.patch_date_typing()) return;
	// the controls bundle is fetched with the first form or dialog
	let tries = 0;
	const timer = setInterval(() => {
		if (frappe_walkthrough.patch_date_typing() || ++tries > 600) clearInterval(timer);
	}, 250);
	$(document).on("form-refresh", frappe_walkthrough.patch_date_typing);
})();
